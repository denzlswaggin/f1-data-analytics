"""Tests for on-track overtake detection and its mart builder.

``detect_overtakes`` is pure (synthetic replay frames, no warehouse);
``build_race_overtakes`` is exercised end to end against a throwaway DuckDB seeded
with a small ``marts.race_replay`` (``duckdb`` is a core dependency, so this runs
in CI without the dbt/telemetry extras).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest
from analytics.overtakes import detect_overtakes
from analytics.pipeline import build_race_overtakes
from ingestion.config import Settings
from ingestion.loaders.warehouse import read_query

EXPECTED_COLUMNS = ["t_s", "for_position", "passer_code", "passed_code", "gap_at_pass_s"]


def _replay(
    order_at: Callable[[float], tuple[int, int]],
    x_of: Callable[[str, float], float],
    n: int = 12,
) -> pd.DataFrame:
    """Build a two-car (A, B) replay frame.

    ``order_at(t)`` returns ``(a_order, b_order)`` for each second; the follower's
    ``gap_to_ahead_s`` is a small 0.4 s, the leader's is 0. ``x_of(driver, t)``
    gives the x coordinate (y is constant) so tests can place the cars together
    (on-track) or far apart (a pitting car).
    """
    rows = []
    for t in np.arange(0.0, float(n), 1.0):
        a_ord, b_ord = order_at(t)
        for code, order in (("A", a_ord), ("B", b_ord)):
            rows.append(
                {
                    "driver_code": code,
                    "t_s": float(t),
                    "x": float(x_of(code, t)),
                    "y": 200.0,
                    "running_order": order,
                    "gap_to_ahead_s": 0.0 if order == 1 else 0.4,
                }
            )
    return pd.DataFrame(rows)


def test_detect_overtakes_clean_pass() -> None:
    # A leads until t=5, then B passes and holds the lead — one clean on-track pass.
    together = lambda code, t: 100.0 + t * 10.0  # noqa: E731 — both cars share the point
    out = detect_overtakes(_replay(lambda t: (1, 2) if t < 5 else (2, 1), together))

    assert list(out.columns) == EXPECTED_COLUMNS
    assert len(out) == 1
    row = out.iloc[0]
    assert row["passer_code"] == "B"
    assert row["passed_code"] == "A"
    assert row["for_position"] == 1
    assert row["t_s"] == pytest.approx(5.0)
    assert row["gap_at_pass_s"] == pytest.approx(0.4)


def test_detect_overtakes_excludes_pit_cycle() -> None:
    # Same order swap, but B is far away (in the pit lane) at the crossover: the
    # progress-gap collapses to ~0 yet the cars are physically apart, so it must NOT
    # count as an on-track overtake.
    def x_of(code: str, t: float) -> float:
        return 100.0 + t * 10.0 + (6000.0 if code == "B" else 0.0)

    out = detect_overtakes(_replay(lambda t: (2, 1) if t < 5 else (1, 2), x_of))
    assert out.empty


def test_detect_overtakes_rejects_flicker() -> None:
    # A one-tick blip where B is momentarily ahead at t=5 then A resumes: the
    # persistence filter must discard the spurious B-over-A "pass".
    together = lambda code, t: 100.0 + t * 10.0  # noqa: E731
    out = detect_overtakes(_replay(lambda t: (2, 1) if t == 5 else (1, 2), together))
    assert (out["passer_code"] == "B").sum() == 0


def test_detect_overtakes_validates_and_handles_empty() -> None:
    together = lambda code, t: 100.0 + t * 10.0  # noqa: E731
    frame = _replay(lambda t: (1, 2), together)
    with pytest.raises(ValueError, match="replay is missing"):
        detect_overtakes(frame.drop(columns=["x"]))
    empty = detect_overtakes(frame.iloc[0:0])
    assert empty.empty
    assert list(empty.columns) == EXPECTED_COLUMNS


def _seed_replay(db_path: Path) -> None:
    together = lambda code, t: 100.0 + t * 10.0  # noqa: E731
    frame = _replay(lambda t: (1, 2) if t < 5 else (2, 1), together)
    frame["season"] = 2026
    frame["round"] = 1
    con = duckdb.connect(str(db_path))
    try:
        con.execute("create schema marts")
        con.register("replay", frame)
        con.execute("create table marts.race_replay as select * from replay")
    finally:
        con.unregister("replay")
        con.close()


def test_build_race_overtakes_materialises_mart(tmp_path: Path) -> None:
    db_path = tmp_path / "f1.duckdb"
    _seed_replay(db_path)
    settings = Settings(warehouse="duckdb", duckdb_path=db_path)

    result = build_race_overtakes(2026, 1, settings=settings)

    assert list(result.columns) == ["season", "round", *EXPECTED_COLUMNS]
    assert len(result) == 1
    assert (result["season"] == 2026).all()
    assert result.iloc[0]["passer_code"] == "B"

    persisted = read_query("select * from marts.race_overtakes", settings)
    assert len(persisted) == 1
    assert persisted.iloc[0]["passed_code"] == "A"
