"""Tests for the race-replay resampler and its mart builder.

``resample_race`` is pure (synthetic frames, no warehouse); ``build_race_replay``
is exercised end to end against a throwaway DuckDB seeded with the two staging
tables it reads (``duckdb`` is a core dependency, so this runs in CI without the
dbt/telemetry extras).
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest
from analytics.pipeline import build_race_replay
from analytics.replay import resample_race
from ingestion.config import Settings
from ingestion.loaders.warehouse import read_query

EXPECTED_COLUMNS = [
    "driver_code",
    "t_s",
    "x",
    "y",
    "running_order",
    "gap_to_leader_s",
    "gap_to_ahead_s",
]


def _synthetic_race() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Two-car, two-lap race: A laps in 10 s, B in 12 s (A clearly faster)."""
    positions = pd.concat(
        [
            pd.DataFrame(
                {
                    "driver_code": "A",
                    "session_time_sec": [0.0, 5.0, 10.0, 15.0, 20.0],
                    "x": [0.0, 5.0, 10.0, 15.0, 20.0],
                    # y != 0 so the start point isn't the (0,0) sentinel that cleaning
                    # drops (real on-track coords are offset, never exactly origin).
                    "y": 50.0,
                }
            ),
            pd.DataFrame(
                {
                    "driver_code": "B",
                    "session_time_sec": [0.0, 6.0, 12.0, 18.0, 24.0],
                    "x": [0.0, 6.0, 12.0, 18.0, 24.0],
                    "y": 100.0,
                }
            ),
        ],
        ignore_index=True,
    )
    laps = pd.DataFrame(
        [
            {"driver_code": "A", "lap_number": 1, "lap_start_sec": 0.0, "lap_time_sec": 10.0},
            {"driver_code": "A", "lap_number": 2, "lap_start_sec": 10.0, "lap_time_sec": 10.0},
            {"driver_code": "B", "lap_number": 1, "lap_start_sec": 0.0, "lap_time_sec": 12.0},
            {"driver_code": "B", "lap_number": 2, "lap_start_sec": 12.0, "lap_time_sec": 12.0},
        ]
    )
    return positions, laps


def test_resample_race_order_gaps_and_window() -> None:
    positions, laps = _synthetic_race()
    out = resample_race(positions, laps, tick_s=1.0)

    assert list(out.columns) == EXPECTED_COLUMNS
    assert out["t_s"].min() == 0.0

    a = out[out["driver_code"] == "A"]
    b = out[out["driver_code"] == "B"]

    # A is faster, so leads whenever both are on track: order 1, ~zero gap.
    assert (a["running_order"] == 1).all()
    np.testing.assert_allclose(a["gap_to_leader_s"].to_numpy(), 0.0, atol=1e-6)

    # X interpolation recovers the straight-line X = session_time.
    a_at_10 = a.loc[np.isclose(a["t_s"], 10.0), "x"].iloc[0]
    assert a_at_10 == pytest.approx(10.0)

    # Active windows: A's positions stop at 20 s, B's at 24 s.
    assert a["t_s"].max() == 20.0
    assert b["t_s"].max() == 24.0

    # While A is present B runs second with a positive gap; once A is gone
    # (finished, positions stop) B inherits P1.
    b_early = b[b["t_s"] <= 20.0]
    b_late = b[b["t_s"] > 20.0]
    assert (b_early["running_order"] == 2).all()
    assert (b_early[b_early["t_s"] >= 12.0]["gap_to_leader_s"] > 0).all()
    assert (b_late["running_order"] == 1).all()


def _retiree_race() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Leader L runs 3 laps (~120 s); retiree R does 1 lap (finishes 40 s) then parks
    at a fixed point to the end — the frozen-ghost case cleaning must retire."""
    t = np.arange(0.0, 121.0, 10.0)
    lead = pd.DataFrame({"driver_code": "L", "session_time_sec": t, "x": 100.0 + t, "y": 300.0})
    # R moves until 40 s, then its feed freezes at (240, 400) for the rest of the race.
    xr = np.where(t <= 40.0, 200.0 + t, 240.0)
    ret = pd.DataFrame({"driver_code": "R", "session_time_sec": t, "x": xr, "y": 400.0})
    positions = pd.concat([lead, ret], ignore_index=True)
    laps = pd.DataFrame(
        [
            {"driver_code": "L", "lap_number": 1, "lap_start_sec": 0.0, "lap_time_sec": 40.0},
            {"driver_code": "L", "lap_number": 2, "lap_start_sec": 40.0, "lap_time_sec": 40.0},
            {"driver_code": "L", "lap_number": 3, "lap_start_sec": 80.0, "lap_time_sec": 40.0},
            {"driver_code": "R", "lap_number": 1, "lap_start_sec": 0.0, "lap_time_sec": 40.0},
        ]
    )
    return positions, laps


def test_resample_race_retires_parked_cars() -> None:
    positions, laps = _retiree_race()
    out = resample_race(positions, laps, tick_s=1.0)

    lead = out[out["driver_code"] == "L"]
    ret = out[out["driver_code"] == "R"]

    # The leader is present to the end (~120 s); the retiree vanishes shortly after
    # its last lap (finish 40 s + 30 s buffer = 70 s), not lingering to the finish.
    assert lead["t_s"].max() >= 115.0
    assert ret["t_s"].max() <= 71.0
    assert out[(out["driver_code"] == "R") & (out["t_s"] >= 90.0)].empty


def test_resample_race_validates_and_handles_empty() -> None:
    positions, laps = _synthetic_race()
    with pytest.raises(ValueError, match="positions is missing"):
        resample_race(positions.drop(columns=["x"]), laps)
    assert resample_race(positions.iloc[0:0], laps).empty


def _seed_warehouse(db_path: Path) -> None:
    positions, laps = _synthetic_race()
    for df in (positions, laps):
        df["season"] = 2026
        df["round"] = 1
        df["session"] = "R"
    con = duckdb.connect(str(db_path))
    try:
        con.execute("create schema staging")
        con.register("positions", positions)
        con.register("laps", laps)
        con.execute("create table staging.stg_positions as select * from positions")
        con.execute("create table staging.stg_laps as select * from laps")
    finally:
        con.unregister("positions")
        con.unregister("laps")
        con.close()


def test_build_race_replay_materialises_mart(tmp_path: Path) -> None:
    db_path = tmp_path / "f1.duckdb"
    _seed_warehouse(db_path)
    settings = Settings(warehouse="duckdb", duckdb_path=db_path)

    result = build_race_replay(2026, 1, tick_s=1.0, settings=settings)

    assert list(result.columns) == ["season", "round", *EXPECTED_COLUMNS]
    assert (result["season"] == 2026).all()
    assert (result["round"] == 1).all()
    assert set(result["driver_code"]) == {"A", "B"}

    persisted = read_query("select * from marts.race_replay", settings)
    assert len(persisted) == len(result)
    assert set(persisted["driver_code"]) == {"A", "B"}
