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
from analytics.pipeline import build_race_replay, build_race_replay_incremental, build_race_replays
from analytics.replay import replay_source_coverage, resample_race, validate_replay_sources
from ingestion.config import Settings
from ingestion.loaders.warehouse import read_query

EXPECTED_COLUMNS = [
    "driver_code",
    "t_s",
    "x",
    "y",
    "lap_number",
    "lap_progress",
    "stint",
    "compound",
    "tyre_life",
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
            {
                "driver_code": "A",
                "lap_number": 1,
                "lap_start_sec": 0.0,
                "lap_time_sec": 10.0,
                "stint": 1,
                "compound": "SOFT",
                "tyre_life": 1,
            },
            {
                "driver_code": "A",
                "lap_number": 2,
                "lap_start_sec": 10.0,
                "lap_time_sec": 10.0,
                "stint": 2,
                "compound": "MEDIUM",
                "tyre_life": 1,
            },
            {
                "driver_code": "B",
                "lap_number": 1,
                "lap_start_sec": 0.0,
                "lap_time_sec": 12.0,
                "stint": 1,
                "compound": "HARD",
                "tyre_life": 1,
            },
            {
                "driver_code": "B",
                "lap_number": 2,
                "lap_start_sec": 12.0,
                "lap_time_sec": 12.0,
                "stint": 1,
                "compound": "HARD",
                "tyre_life": 2,
            },
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


def test_resample_race_adds_lap_progress_and_tyre_state() -> None:
    positions, laps = _synthetic_race()
    out = resample_race(positions, laps, tick_s=1.0)
    a = out[out["driver_code"] == "A"].set_index("t_s")

    assert a.loc[5.0, "lap_number"] == 1
    assert a.loc[5.0, "lap_progress"] == pytest.approx(0.5)
    assert a.loc[5.0, "stint"] == 1
    assert a.loc[5.0, "compound"] == "SOFT"
    assert a.loc[5.0, "tyre_life"] == 1

    # The new stint becomes active exactly at the second lap's start.
    assert a.loc[10.0, "lap_number"] == 2
    assert a.loc[10.0, "lap_progress"] == pytest.approx(0.0)
    assert a.loc[10.0, "stint"] == 2
    assert a.loc[10.0, "compound"] == "MEDIUM"
    assert a.loc[10.0, "tyre_life"] == 1
    assert a.loc[20.0, "lap_progress"] == pytest.approx(1.0)


def test_resample_race_keeps_original_lap_input_contract() -> None:
    positions, laps = _synthetic_race()
    laps = laps.drop(columns=["stint", "compound", "tyre_life"])

    out = resample_race(positions, laps, tick_s=1.0)

    assert out["lap_number"].notna().all()
    assert out["lap_progress"].notna().all()
    assert out[["stint", "compound", "tyre_life"]].isna().all().all()


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
    out = resample_race(positions, laps, tick_s=1.0, retire_buffer_s=5.0)

    lead = out[out["driver_code"] == "L"]
    ret = out[out["driver_code"] == "R"]

    # The leader keeps moving to the end (~120 s). The retiree stops moving at 40 s,
    # so with a 5 s buffer it vanishes at ~45 s — not lingering frozen to the finish.
    assert lead["t_s"].max() >= 115.0
    assert ret["t_s"].max() <= 46.0
    assert out[(out["driver_code"] == "R") & (out["t_s"] >= 60.0)].empty


def test_resample_race_retire_buffer_is_tunable() -> None:
    positions, laps = _retiree_race()
    # A longer buffer keeps the retiree (stops at 40 s) on the map for longer.
    short = resample_race(positions, laps, tick_s=1.0, retire_buffer_s=0.0)
    long = resample_race(positions, laps, tick_s=1.0, retire_buffer_s=20.0)
    short_r = short[short["driver_code"] == "R"]["t_s"].max()
    long_r = long[long["driver_code"] == "R"]["t_s"].max()
    assert short_r == pytest.approx(40.0, abs=1.0)
    assert long_r == pytest.approx(60.0, abs=1.0)


def test_resample_race_clamps_recovered_retiree() -> None:
    # R completes 1 lap (finishes 40 s) but its position keeps moving to the end (as
    # if recovered/craned) — the safety cap must retire it, not show it to the flag.
    t = np.arange(0.0, 121.0, 10.0)
    lead = pd.DataFrame({"driver_code": "L", "session_time_sec": t, "x": 100.0 + 5 * t, "y": 300.0})
    ret = pd.DataFrame({"driver_code": "R", "session_time_sec": t, "x": 200.0 + 5 * t, "y": 400.0})
    positions = pd.concat([lead, ret], ignore_index=True)
    laps = pd.DataFrame(
        [
            {"driver_code": "L", "lap_number": 1, "lap_start_sec": 0.0, "lap_time_sec": 40.0},
            {"driver_code": "L", "lap_number": 2, "lap_start_sec": 40.0, "lap_time_sec": 40.0},
            {"driver_code": "L", "lap_number": 3, "lap_start_sec": 80.0, "lap_time_sec": 40.0},
            {"driver_code": "R", "lap_number": 1, "lap_start_sec": 0.0, "lap_time_sec": 40.0},
        ]
    )
    out = resample_race(positions, laps, tick_s=1.0, retire_buffer_s=5.0, max_linger_s=30.0)
    ret_out = out[out["driver_code"] == "R"]
    # R never stops moving, but is clamped at its last lap (40 s) + 30 s = 70 s.
    assert ret_out["t_s"].max() == pytest.approx(70.0, abs=1.0)
    assert out[(out["driver_code"] == "R") & (out["t_s"] >= 90.0)].empty
    # The leader (still racing) is unaffected and runs to the end.
    assert out[out["driver_code"] == "L"]["t_s"].max() >= 115.0


def test_resample_race_validates_and_handles_empty() -> None:
    positions, laps = _synthetic_race()
    with pytest.raises(ValueError, match="positions is missing"):
        resample_race(positions.drop(columns=["x"]), laps)
    empty = resample_race(positions.iloc[0:0], laps)
    assert empty.empty
    assert list(empty.columns) == EXPECTED_COLUMNS


def test_replay_source_coverage_rejects_truncated_position_feed() -> None:
    positions, laps = _synthetic_race()

    assert replay_source_coverage(positions, laps) == pytest.approx(22.0 / 24.0)
    validate_replay_sources(positions, laps)

    truncated = positions[positions["session_time_sec"] <= 5.0]
    with pytest.raises(ValueError, match="position feed covers only"):
        validate_replay_sources(truncated, laps)


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


def test_incremental_replay_preserves_other_rounds(tmp_path: Path) -> None:
    db_path = tmp_path / "f1.duckdb"
    _seed_warehouse(db_path)
    settings = Settings(warehouse="duckdb", duckdb_path=db_path)

    first = build_race_replay_incremental(2026, 1, tick_s=1.0, settings=settings)
    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            "insert into marts.race_replay "
            "select season, 2 as round, driver_code, t_s, x, y, lap_number, lap_progress, "
            "stint, compound, tyre_life, running_order, gap_to_leader_s, gap_to_ahead_s "
            "from marts.race_replay where round = 1"
        )
    finally:
        con.close()

    corrected = build_race_replay_incremental(2026, 1, tick_s=2.0, settings=settings)
    counts = read_query(
        "select round, count(*) as n from marts.race_replay group by round order by round",
        settings,
    )

    assert len(corrected) < len(first)
    assert dict(zip(counts["round"], counts["n"], strict=True)) == {
        1: len(corrected),
        2: len(first),
    }


def test_multi_race_builder_skips_truncated_partitions(tmp_path: Path) -> None:
    db_path = tmp_path / "f1.duckdb"
    _seed_warehouse(db_path)
    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            "insert into staging.stg_laps "
            "(driver_code, lap_number, lap_start_sec, lap_time_sec, season, round, session) "
            "select driver_code, lap_number, lap_start_sec, lap_time_sec, season, 2, session "
            "from staging.stg_laps where round = 1"
        )
        con.execute(
            "insert into staging.stg_positions "
            "(driver_code, session_time_sec, x, y, season, round, session) "
            "select driver_code, session_time_sec, x, y, season, 2, session "
            "from staging.stg_positions where round = 1 and session_time_sec <= 5"
        )
    finally:
        con.close()

    settings = Settings(warehouse="duckdb", duckdb_path=db_path)
    result = build_race_replays(2026, [1, 2], tick_s=1.0, settings=settings)

    assert set(result["round"]) == {1}
