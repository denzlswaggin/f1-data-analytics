"""Tests for clean-air post-stop pace settling analysis."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pytest
from analytics.pipeline import build_tyre_warmup, build_tyre_warmup_incremental
from analytics.tyre_warmup import (
    TYRE_WARMUP_COLUMNS,
    TYRE_WARMUP_LAP_COLUMNS,
    analyse_tyre_warmup,
)
from ingestion.config import Settings
from ingestion.loaders.warehouse import read_query


def _laps(
    *,
    compound: str = "HARD",
    fresh: bool = True,
    stint_end: int = 22,
    include_transition: bool = True,
) -> pd.DataFrame:
    rows = [
        {
            "season": 2026,
            "round": 1,
            "race_name": "Test GP",
            "driver_code": "AAA",
            "driver_name": "Driver AAA",
            "team": "Test Team",
            "lap_number": lap,
            "stint": 2,
            "compound": compound,
            "tyre_life": lap - 9,
            "is_fresh_tyre": fresh,
            "lap_time_sec": 90.0,
            "track_status": "1",
        }
        for lap in range(10, stint_end + 1)
    ]
    if include_transition:
        rows.insert(
            0,
            {
                **rows[0],
                "lap_number": 9,
                "stint": 1,
                "compound": "MEDIUM",
                "tyre_life": 12,
            },
        )
    return pd.DataFrame(rows)


def _expected(offset: int) -> float:
    return 1.0 - 0.1 * offset


def _traffic(
    deltas: dict[int, float] | None = None,
    states: dict[int, str] | None = None,
    coverage: dict[int, float] | None = None,
) -> pd.DataFrame:
    controlled = {
        11: 2.1,
        12: 1.4,
        13: 0.8,
        **{lap: _expected(lap - 10) for lap in range(14, 23)},
    }
    if deltas is not None:
        controlled.update(deltas)
    states = states or {}
    coverage = coverage or {}
    return pd.DataFrame(
        [
            {
                "season": 2026,
                "round": 1,
                "driver_code": "AAA",
                "stint": 2,
                "lap_number": lap,
                "air_state": states.get(lap, "clean_air"),
                "controlled_pace_delta_sec": delta,
                "replay_coverage_pct": coverage.get(lap, 100.0),
                "traffic_share": 0.0,
                "median_gap_to_ahead_s": 4.0,
            }
            for lap, delta in controlled.items()
        ]
    )


def test_fits_mature_trend_and_measures_time_to_pace() -> None:
    result = analyse_tyre_warmup(_laps(), _traffic())

    stint = result.summary.iloc[0]
    assert bool(stint["warmup_eligible"])
    assert bool(stint["crossover_eligible"])
    assert stint["baseline_slope_sec_per_lap"] == pytest.approx(-0.1)
    assert stint["baseline_mad_sec"] == pytest.approx(0.0)
    assert stint["first_flying_warmup_loss_sec"] == pytest.approx(1.2)
    assert stint["second_flying_warmup_loss_sec"] == pytest.approx(0.6)
    assert stint["first_two_lap_warmup_cost_sec"] == pytest.approx(1.8)
    assert stint["stable_window_start_lap"] == 13
    assert stint["time_to_pace_laps"] == 4
    assert stint["confidence"] == "High"


def test_out_lap_is_never_in_pace_evidence() -> None:
    result = analyse_tyre_warmup(_laps(), _traffic())

    assert result.laps["lap_number"].min() == 11
    assert result.laps["post_stop_offset"].tolist() == list(range(1, 13))
    assert result.summary["out_lap"].iloc[0] == 10


def test_requires_contiguous_stint_transition() -> None:
    result = analyse_tyre_warmup(_laps(include_transition=False), _traffic())

    assert not bool(result.summary["warmup_eligible"].iloc[0])
    assert result.summary["exclusion_reason"].iloc[0] == "Stint transition is not contiguous"


def test_requires_clean_well_covered_first_flying_lap() -> None:
    traffic = _traffic(states={11: "traffic"})
    result = analyse_tyre_warmup(_laps(), traffic)
    assert result.summary["exclusion_reason"].iloc[0] == "First flying lap was not in clean air"

    traffic = _traffic(coverage={11: 79.9})
    result = analyse_tyre_warmup(_laps(), traffic)
    assert result.summary["exclusion_reason"].iloc[0] == (
        "Replay coverage below 80% on first flying lap"
    )


def test_requires_three_clean_mature_reference_laps() -> None:
    states = dict.fromkeys((17, 18, 19, 20), "traffic")
    result = analyse_tyre_warmup(_laps(), _traffic(states=states))

    assert not bool(result.summary["warmup_eligible"].iloc[0])
    assert result.summary["exclusion_reason"].iloc[0] == (
        "Fewer than three clean mature-reference laps"
    )


@pytest.mark.parametrize(
    ("laps", "reason"),
    [
        (_laps(compound="INTERMEDIATE"), "Unsupported or wet-weather compound"),
        (_laps(stint_end=19), "Stint shorter than 11 laps"),
    ],
)
def test_retains_ineligible_stints(laps: pd.DataFrame, reason: str) -> None:
    result = analyse_tyre_warmup(laps, _traffic())

    assert len(result.summary) == 1
    assert not bool(result.summary["warmup_eligible"].iloc[0])
    assert result.summary["exclusion_reason"].iloc[0] == reason


def test_used_tyres_are_eligible_but_cannot_be_high_confidence() -> None:
    result = analyse_tyre_warmup(_laps(fresh=False), _traffic())

    assert bool(result.summary["warmup_eligible"].iloc[0])
    assert result.summary["confidence"].iloc[0] == "Medium"


def test_non_green_lap_is_not_used_for_mature_trend() -> None:
    laps = _laps()
    laps.loc[laps["lap_number"].eq(17), "track_status"] = "12"
    result = analyse_tyre_warmup(laps, _traffic())

    lap = result.laps.loc[result.laps["lap_number"].eq(17)].iloc[0]
    assert not bool(lap["used_for_baseline"])
    assert lap["lap_exclusion_reason"] == "Lap was not green"
    assert result.summary["mature_reference_laps"].iloc[0] == 5


def test_stable_pace_requires_two_consecutive_clean_laps() -> None:
    controlled = {11: _expected(1) + 0.1, 12: _expected(2) + 0.8}
    result = analyse_tyre_warmup(_laps(), _traffic(controlled))

    assert result.summary["stable_window_start_lap"].iloc[0] == 13
    assert result.summary["time_to_pace_laps"].iloc[0] == 4


def test_complete_unsettled_window_is_right_censored() -> None:
    controlled = {10 + offset: _expected(offset) + 0.8 for offset in range(1, 7)}
    result = analyse_tyre_warmup(_laps(), _traffic(controlled))

    stint = result.summary.iloc[0]
    assert not bool(stint["stable_pace_achieved"])
    assert bool(stint["right_censored"])
    assert bool(stint["crossover_eligible"])
    assert pd.isna(stint["time_to_pace_laps"])


def test_missing_evaluation_lap_is_incomplete_not_censored() -> None:
    controlled = {10 + offset: _expected(offset) + 0.8 for offset in range(1, 7)}
    result = analyse_tyre_warmup(_laps(), _traffic(controlled, states={13: "traffic"}))

    stint = result.summary.iloc[0]
    assert not bool(stint["observation_complete"])
    assert not bool(stint["right_censored"])
    assert not bool(stint["crossover_eligible"])


def test_rejects_implausibly_steep_mature_trend() -> None:
    controlled = {lap: float(lap - 17) for lap in range(17, 23)}
    result = analyse_tyre_warmup(_laps(), _traffic(controlled))

    assert result.summary["exclusion_reason"].iloc[0] == "Mature-pace trend is too steep"


def test_empty_result_has_stable_typed_schemas() -> None:
    result = analyse_tyre_warmup(_laps().iloc[0:0], _traffic().iloc[0:0])

    assert result.summary.columns.tolist() == TYRE_WARMUP_COLUMNS
    assert result.laps.columns.tolist() == TYRE_WARMUP_LAP_COLUMNS
    assert str(result.summary["warmup_eligible"].dtype) == "boolean"
    assert str(result.laps["warmup_loss_sec"].dtype) == "float64"


def test_validates_contracts_and_threshold() -> None:
    with pytest.raises(ValueError, match="laps is missing columns"):
        analyse_tyre_warmup(_laps().drop(columns="team"), _traffic())
    with pytest.raises(ValueError, match="traffic_laps is missing columns"):
        analyse_tyre_warmup(_laps(), _traffic().drop(columns="air_state"))
    with pytest.raises(ValueError, match="stable_band_sec"):
        analyse_tyre_warmup(_laps(), _traffic(), stable_band_sec=0)


def _seed_warehouse(path: Path) -> Settings:
    settings = Settings(warehouse="duckdb", duckdb_path=path)
    laps = _laps().assign(session="R")
    races = laps.loc[:, ["season", "round", "race_name"]].drop_duplicates()
    codes = laps.loc[:, ["season", "driver_code", "driver_name"]].drop_duplicates()
    connection = duckdb.connect(str(path))
    try:
        connection.execute("create schema staging")
        connection.execute("create schema marts")
        for schema, name, frame in (
            ("staging", "stg_laps", laps),
            ("staging", "stg_races", races),
            ("staging", "stg_driver_codes", codes),
            ("marts", "traffic_adjusted_laps", _traffic()),
        ):
            connection.register("incoming", frame)
            connection.execute(f"create table {schema}.{name} as select * from incoming")
            connection.unregister("incoming")
    finally:
        connection.close()
    return settings


def test_builder_materialises_both_tyre_warmup_marts(tmp_path: Path) -> None:
    settings = _seed_warehouse(tmp_path / "tyre-warmup.duckdb")

    result = build_tyre_warmup(2026, 1, settings=settings)

    summary = read_query("select * from marts.tyre_warmup", settings)
    evidence = read_query("select * from marts.tyre_warmup_laps", settings)
    assert len(summary) == len(result.summary) == 1
    assert len(evidence) == len(result.laps) == 12
    assert bool(summary["warmup_eligible"].iloc[0])


def test_incremental_builder_preserves_other_races(tmp_path: Path) -> None:
    settings = _seed_warehouse(tmp_path / "tyre-warmup-incremental.duckdb")
    result = build_tyre_warmup(2026, 1, settings=settings)
    summary_copy = result.summary.assign(round=2)
    evidence_copy = result.laps.assign(round=2)
    connection = duckdb.connect(str(settings.duckdb_path))
    try:
        connection.register("summary_copy", summary_copy)
        connection.register("evidence_copy", evidence_copy)
        connection.execute("insert into marts.tyre_warmup by name select * from summary_copy")
        connection.execute("insert into marts.tyre_warmup_laps by name select * from evidence_copy")
    finally:
        connection.close()

    build_tyre_warmup_incremental(2026, 1, settings=settings)

    rounds = read_query(
        "select round, count(*) as rows from marts.tyre_warmup group by round order by round",
        settings,
    )
    assert rounds["round"].tolist() == [1, 2]
    assert rounds["rows"].tolist() == [1, 1]
