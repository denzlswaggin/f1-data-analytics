"""Synthetic tests for pairwise pit-window effectiveness."""

from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest
from analytics.pipeline import (
    build_pit_window_effectiveness,
    build_pit_window_effectiveness_incremental,
)
from analytics.pit_window import PIT_WINDOW_COLUMNS, _prepare_laps, analyse_pit_windows
from ingestion.config import Settings
from ingestion.loaders.warehouse import read_query


@pytest.mark.parametrize("missing_time", [None, 0.0, -1.0])
def test_missing_pit_timing_does_not_shift_inferred_boundary(missing_time: float | None) -> None:
    laps = _race_laps()
    laps.loc[laps["driver_code"].eq("A") & laps["lap_number"].eq(3), "lap_time_sec"] = missing_time
    prepared = _prepare_laps(laps)
    driver = prepared.loc[prepared["driver_code"].eq("A")].set_index("lap_number")
    assert 3 not in driver.index
    assert not bool(driver.loc[2, "is_pit_in_lap"])
    assert bool(driver.loc[4, "is_pit_out_lap"])


def test_additional_actual_pit_without_stint_change_is_retained_as_excluded() -> None:
    stops = pd.concat([_stops(), _stops().iloc[[0]].assign(pit_lap=5)], ignore_index=True)
    result = analyse_pit_windows(_race_laps(), stops)
    assert len(result) == 1
    assert not bool(result.iloc[0]["eligible"])
    assert result.iloc[0]["exclusion_reason"] == "Additional stop in window"
    assert pd.isna(result.iloc[0]["net_time_gain_sec"])


def _race_laps(
    *,
    a_pit_lap: int = 3,
    b_pit_lap: int = 5,
    after_gap: float = -1.0,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    b_ends = {lap: 100.0 * lap for lap in range(1, 10)}
    a_ends = {
        1: 102.0,
        2: 202.0,
        3: 302.0,
        4: 401.0,
        5: 500.0,
        6: b_ends[6] + after_gap,
        7: b_ends[7] + after_gap,
        8: b_ends[8] + after_gap,
        9: b_ends[9] + after_gap,
    }
    for code, ends, pit_lap in (("A", a_ends, a_pit_lap), ("B", b_ends, b_pit_lap)):
        previous_end = 0.0
        for lap in range(1, 10):
            end = ends[lap]
            second_stint = lap > pit_lap
            rows.append(
                {
                    "season": 2026,
                    "round": 4,
                    "race_name": "Test Grand Prix",
                    "driver_code": code,
                    "driver_name": f"Driver {code}",
                    "team": f"Team {code}",
                    "lap_number": lap,
                    "stint": 2 if second_stint else 1,
                    "compound": "HARD" if second_stint else "MEDIUM",
                    "is_fresh_tyre": second_stint,
                    "tyre_life": lap - pit_lap if second_stint else lap,
                    "position": (
                        2
                        if code == "A" and lap <= b_pit_lap
                        else 1
                        if code == "A" and after_gap < 0
                        else 1
                        if code == "B" and (lap <= b_pit_lap or after_gap >= 0)
                        else 2
                    ),
                    "lap_start_sec": previous_end,
                    "lap_time_sec": end - previous_end,
                    "track_status": "1",
                }
            )
            previous_end = end
    return pd.DataFrame(rows)


def _stops(a_duration: float = 2.5, b_duration: float = 3.0) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "season": 2026,
                "round": 4,
                "driver_code": "A",
                "pit_lap": 3,
                "duration_sec": a_duration,
            },
            {
                "season": 2026,
                "round": 4,
                "driver_code": "B",
                "pit_lap": 5,
                "duration_sec": b_duration,
            },
        ]
    )


def test_measures_successful_undercut_on_common_lap_checkpoints() -> None:
    result = analyse_pit_windows(_race_laps(), _stops())

    assert len(result) == 1
    row = result.iloc[0]
    assert row["checkpoint_before_lap"] == 2
    assert row["checkpoint_after_lap"] == 6
    assert row["gap_before_sec"] == pytest.approx(2.0)
    assert row["gap_after_sec"] == pytest.approx(-1.0)
    assert row["net_time_gain_sec"] == pytest.approx(3.0)
    assert row["stop_duration_delta_sec"] == pytest.approx(-0.5)
    assert row["on_track_gain_sec"] == pytest.approx(2.5)
    assert bool(row["position_flip"])
    assert bool(row["eligible"])
    assert row["confidence"] == "high"
    assert row["opportunity_type"] == "Undercut opportunity"
    assert row["outcome_label"] == "Undercut completed"


def test_labels_overcut_when_earlier_driver_loses_time() -> None:
    result = analyse_pit_windows(_race_laps(after_gap=4.0), _stops())

    row = result.iloc[0]
    assert row["net_time_gain_sec"] == pytest.approx(-2.0)
    assert not bool(row["position_flip"])
    assert row["outcome_label"] == "Late stop gained"


def test_same_lap_stops_are_not_an_undercut_or_overcut_window() -> None:
    result = analyse_pit_windows(_race_laps(a_pit_lap=4, b_pit_lap=4))

    assert result.empty
    assert list(result.columns) == PIT_WINDOW_COLUMNS
    assert str(result["season"].dtype) == "Int64"
    assert str(result["net_time_gain_sec"].dtype) == "float64"
    assert str(result["eligible"].dtype) == "boolean"


def test_distant_cars_are_not_treated_as_strategy_rivals() -> None:
    laps = _race_laps()
    mask = (laps["driver_code"] == "A") & (laps["lap_number"] <= 2)
    laps.loc[mask, "lap_start_sec"] += 20
    laps.loc[mask, "lap_time_sec"] = 100

    assert analyse_pit_windows(laps).empty


def test_race_control_window_is_retained_but_excluded() -> None:
    laps = _race_laps()
    laps.loc[(laps["driver_code"] == "B") & (laps["lap_number"] == 4), "track_status"] = "4"

    row = analyse_pit_windows(laps, _stops()).iloc[0]
    assert not bool(row["eligible"])
    assert not bool(row["window_green"])
    assert row["exclusion_reason"] == "Race-control affected"
    assert row["confidence"] == "excluded"
    assert row["outcome_label"] == "Excluded"
    assert np.isnan(row["net_time_gain_sec"])


def test_missing_stationary_times_keep_cycle_with_reduced_confidence() -> None:
    result = analyse_pit_windows(_race_laps())

    row = result.iloc[0]
    assert bool(row["eligible"])
    assert row["confidence"] == "medium"
    assert np.isnan(row["stop_duration_delta_sec"])
    assert np.isnan(row["on_track_gain_sec"])


def test_requires_input_contract_and_valid_thresholds() -> None:
    with pytest.raises(ValueError, match="laps is missing columns"):
        analyse_pit_windows(pd.DataFrame({"season": [2026]}))
    with pytest.raises(ValueError, match="max_stop_separation"):
        analyse_pit_windows(_race_laps(), max_stop_separation_laps=0)
    with pytest.raises(ValueError, match="thresholds"):
        analyse_pit_windows(_race_laps(), max_pre_gap_sec=0)


def test_empty_typed_input_returns_stable_schema() -> None:
    result = analyse_pit_windows(_race_laps().iloc[0:0])

    assert result.empty
    assert list(result.columns) == PIT_WINDOW_COLUMNS


def _seed_warehouse(path: Path) -> Settings:
    settings = Settings(warehouse="duckdb", duckdb_path=path)
    laps = _race_laps().assign(session="R")
    races = laps.loc[:, ["season", "round", "race_name"]].drop_duplicates()
    codes = pd.DataFrame(
        [
            {
                "season": 2026,
                "driver_code": code,
                "driver_id": f"driver_{code.lower()}",
                "driver_name": f"Driver {code}",
            }
            for code in ("A", "B")
        ]
    )
    stops = (
        _stops()
        .merge(codes, on=["season", "driver_code"])
        .loc[:, ["season", "round", "driver_id", "pit_lap", "duration_sec"]]
    )
    connection = duckdb.connect(str(path))
    try:
        connection.execute("create schema staging")
        for name, frame in (
            ("stg_laps", laps),
            ("stg_races", races),
            ("stg_driver_codes", codes),
            ("stg_pitstops", stops),
        ):
            connection.register("incoming", frame)
            connection.execute(f"create table staging.{name} as select * from incoming")
            connection.unregister("incoming")
    finally:
        connection.close()
    return settings


def test_builder_materialises_pit_window_mart(tmp_path: Path) -> None:
    settings = _seed_warehouse(tmp_path / "pit-window.duckdb")

    result = build_pit_window_effectiveness(2026, 4, settings=settings)
    materialised = read_query("select * from marts.pit_window_effectiveness", settings)

    assert len(materialised) == len(result) == 1
    assert bool(materialised["eligible"].iloc[0])
    assert materialised["net_time_gain_sec"].iloc[0] == pytest.approx(3.0)


def test_incremental_builder_preserves_other_races(tmp_path: Path) -> None:
    settings = _seed_warehouse(tmp_path / "pit-window-incremental.duckdb")
    result = build_pit_window_effectiveness(2026, 4, settings=settings)
    copy = result.assign(round=3)
    connection = duckdb.connect(str(settings.duckdb_path))
    try:
        connection.register("copy", copy)
        connection.execute("insert into marts.pit_window_effectiveness by name select * from copy")
    finally:
        connection.close()

    build_pit_window_effectiveness_incremental(2026, 4, settings=settings)

    rounds = read_query(
        "select round, count(*) as rows from marts.pit_window_effectiveness "
        "group by round order by round",
        settings,
    )
    assert rounds["round"].tolist() == [3, 4]
    assert rounds["rows"].tolist() == [1, 1]
