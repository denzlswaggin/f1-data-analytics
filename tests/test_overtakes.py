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

EXPECTED_COLUMNS = [
    "t_s",
    "for_position",
    "passer_code",
    "passed_code",
    "gap_at_pass_s",
    "confidence",
    "evidence",
    "reason",
]


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
    assert row["confidence"] == pytest.approx(0.96)
    assert "distance=0.00" in row["evidence"]
    assert "persistence=confirmed" in row["evidence"]
    assert row["reason"] == "clean_adjacent_swap"


@pytest.mark.parametrize("failure", ["truncated", "missing_car", "missing_tick", "large_gap"])
def test_persistence_requires_observed_continuous_followup(failure: str) -> None:
    frame = _replay(lambda t: (1, 2) if t < 5 else (2, 1), lambda code, t: 100 + t * 10)
    if failure == "truncated":
        frame = frame.loc[frame.t_s < 8]
    elif failure == "missing_car":
        frame.loc[(frame.driver_code == "A") & (frame.t_s == 6), "running_order"] = np.nan
    elif failure == "missing_tick":
        frame = frame.loc[frame.t_s != 6]
    else:
        frame = frame.loc[(frame.t_s <= 5) | (frame.t_s >= 10)]
    assert detect_overtakes(frame).empty


def test_exact_persistence_endpoint_is_sufficient() -> None:
    frame = _replay(lambda t: (1, 2) if t < 5 else (2, 1), lambda code, t: 100 + t * 10, n=9)
    assert len(detect_overtakes(frame)) == 1


@pytest.mark.parametrize("gap", [-0.1, float("-inf"), float("inf")])
def test_invalid_completion_gap_is_not_evidence(gap: float) -> None:
    frame = _replay(lambda t: (1, 2) if t < 5 else (2, 1), lambda code, t: 100 + t * 10)
    frame.loc[(frame.driver_code == "A") & (frame.t_s == 5), "gap_to_ahead_s"] = gap
    assert detect_overtakes(frame).empty


def test_conflicting_driver_tick_is_rejected() -> None:
    frame = _replay(lambda t: (1, 2) if t < 5 else (2, 1), lambda code, t: 100 + t * 10)
    extra = frame.iloc[[10]].copy()
    extra["running_order"] = 1
    with pytest.raises(ValueError, match="Conflicting replay samples"):
        detect_overtakes(pd.concat([frame, extra]))


def test_detect_overtakes_bridges_one_incomplete_ranking_tick() -> None:
    # B's timing update is absent at t=5, then the adjacent A/B order resolves at
    # t=6. The detector may bridge this short incomplete transition.
    together = lambda code, t: 100.0 + t * 10.0  # noqa: E731
    frame = _replay(lambda t: (1, 2) if t < 6 else (2, 1), together)
    missing_b = (frame["driver_code"] == "B") & (frame["t_s"] == 5)
    frame.loc[missing_b, "running_order"] = np.nan

    out = detect_overtakes(frame)

    assert len(out) == 1
    row = out.iloc[0]
    assert row["t_s"] == pytest.approx(6.0)
    assert row["passer_code"] == "B"
    assert row["reason"] == "adjacent_swap_after_short_transition"
    assert "transition_s=2.00" in row["evidence"]
    assert 0.0 <= row["confidence"] <= 1.0


def test_detect_overtakes_rejects_distant_multi_tick_transition() -> None:
    # B falls to P3 while the order changes. That is not a clean adjacent A/B
    # exchange even though the final frame puts B ahead of A.
    together = lambda code, t: 100.0 + t * 10.0  # noqa: E731
    frame = _replay(
        lambda t: (1, 2) if t < 5 else ((1, 3) if t == 5 else (2, 1)),
        together,
    )

    out = detect_overtakes(frame)

    assert out.empty


def test_detect_overtakes_does_not_bridge_stale_transition() -> None:
    # Missing timing for longer than the two-second transition window must not
    # turn an old adjacent order into evidence for a new pass.
    together = lambda code, t: 100.0 + t * 10.0  # noqa: E731
    frame = _replay(lambda t: (1, 2) if t < 7 else (2, 1), together)
    missing_b = (frame["driver_code"] == "B") & frame["t_s"].isin([5.0, 6.0])
    frame.loc[missing_b, "running_order"] = np.nan

    out = detect_overtakes(frame)

    assert out.empty


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
        con.execute("create schema staging")
        con.execute("""create table staging.stg_laps as
            select distinct season, round, driver_code, 'R' as session,
                1000.0 as lap_start_sec, null::double as pit_in_time_sec,
                null::double as pit_out_time_sec from replay""")
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


@pytest.mark.parametrize("driver", ["A", "B"])
@pytest.mark.parametrize("entry,exit", [(1004.0, 1006.0), (1005.0, 1006.0), (1004.0, 1005.0)])
def test_observed_pit_interval_blocks_nearby_swap(driver: str, entry: float, exit: float) -> None:
    frame = _replay(lambda t: (1, 2) if t < 5 else (2, 1), lambda code, t: 100 + t * 10)
    laps = pd.DataFrame(
        {
            "driver_code": [driver, driver],
            "lap_start_sec": [1000.0, 1005.0],
            "pit_in_time_sec": [entry, np.nan],
            "pit_out_time_sec": [np.nan, exit],
        }
    )
    assert len(detect_overtakes(frame)) == 1
    assert detect_overtakes(frame, pit_laps=laps).empty


def test_pass_outside_observed_pit_interval_remains_unverified_model_event() -> None:
    frame = _replay(lambda t: (1, 2) if t < 5 else (2, 1), lambda code, t: 100 + t * 10)
    laps = pd.DataFrame(
        {
            "driver_code": ["A", "A"],
            "lap_start_sec": [1000.0, 1003.0],
            "pit_in_time_sec": [1001.0, np.nan],
            "pit_out_time_sec": [np.nan, 1004.0],
        }
    )
    result = detect_overtakes(frame, pit_laps=laps)
    assert len(result) == 1
    assert "pit_interval_check=no_observed_overlap" in result.iloc[0].evidence


def test_standalone_builder_uses_pit_observations(tmp_path: Path) -> None:
    path = tmp_path / "f1.duckdb"
    _seed_replay(path)
    with duckdb.connect(str(path)) as connection:
        connection.execute("""update staging.stg_laps set
            pit_in_time_sec=1004.0, pit_out_time_sec=1006.0 where driver_code='A'""")
    assert build_race_overtakes(2026, 1, Settings(duckdb_path=path)).empty
