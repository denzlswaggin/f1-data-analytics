from pathlib import Path

import duckdb
import pytest
from analytics.pit_timing import METHODOLOGY_VERSION, _empty_result

ROOT = Path(__file__).parents[1]
PAGE = ROOT / "dashboard" / "pages" / "pit-timing-sensitivity.md"
SUMMARY_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "pit_timing_sensitivity.sql"
SCENARIO_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "pit_timing_scenarios.sql"
COVERAGE_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "data_coverage.sql"
NAV = ROOT / "dashboard" / "components" / "AppNav.svelte"


def test_page_exposes_scenarios_uncertainty_and_limitations() -> None:
    page = PAGE.read_text(encoding="utf-8")

    assert "best_supported_shift_laps" in page
    assert "delta_p25_sec" in page
    assert "f1.pit_timing_scenarios" in page
    assert "Negative Δ is faster" in page
    assert "not a strategy oracle" in page
    assert "Pit duration is displayed" in page
    assert "five other clean-air field peers" in page
    assert "not an optimal pit" in page
    assert "middle 50% resampling spread" in page
    assert "not a calibrated probability" in page
    assert "Fractional bootstrap wins" in page
    assert "bootstrap_valid_samples" in page
    assert "old_extrapolation_laps" in page
    assert "new_extrapolation_laps" in page


def test_sources_publish_both_marts_and_typed_sentinels() -> None:
    summary = SUMMARY_SOURCE.read_text(encoding="utf-8")
    scenarios = SCENARIO_SOURCE.read_text(encoding="utf-8")
    coverage = COVERAGE_SOURCE.read_text(encoding="utf-8")

    assert "from marts.pit_timing_sensitivity" in summary
    assert "best_shift_win_pct" in summary
    assert "where not exists" in summary
    assert "from marts.pit_timing_scenarios" in scenarios
    assert "delta_vs_actual_sec" in scenarios
    assert "where not exists" in scenarios
    assert "'pit_timing'" in coverage


def test_race_navigation_links_to_pit_timing_page() -> None:
    navigation = NAV.read_text(encoding="utf-8")
    assert "{ label: 'Pit timing sensitivity', path: 'pit-timing-sensitivity' }" in navigation


@pytest.mark.parametrize("populated", [False, True])
@pytest.mark.parametrize("table", ["pit_timing_sensitivity", "pit_timing_scenarios"])
def test_sources_execute_with_typed_empty_and_populated_contracts(
    table: str, populated: bool
) -> None:
    result = _empty_result()
    summary = table == "pit_timing_sensitivity"
    source = SUMMARY_SOURCE if summary else SCENARIO_SOURCE
    frame = result.summary if summary else result.scenarios
    values: dict[str, object] = {
        "season": 2026,
        "round": 1,
        "race_name": "Test Grand Prix",
        "driver_code": "AAA",
        "methodology_version": METHODOLOGY_VERSION,
    }
    values.update(
        {
            "bootstrap_requested_samples": 300,
            "bootstrap_valid_samples": 299,
            "bootstrap_attempted_samples": 350,
            "boundary_minimum": True,
            "best_old_extrapolation_laps": 1.1,
            "best_new_extrapolation_laps": 2.2,
            "actual_old_extrapolation_laps": 3.3,
            "actual_new_extrapolation_laps": 4.4,
        }
        if summary
        else {"old_extrapolation_laps": 1.1, "new_extrapolation_laps": 2.2}
    )
    with duckdb.connect() as connection:
        connection.execute("create schema marts")
        connection.register("empty_contract", frame)
        connection.execute(f"create table marts.{table} as select * from empty_contract")
        if populated:
            columns = ", ".join(values)
            placeholders = ", ".join("?" for _ in values)
            connection.execute(
                f"insert into marts.{table} ({columns}) values ({placeholders})",
                list(values.values()),
            )
        published = connection.execute(source.read_text(encoding="utf-8")).fetchdf()
    assert len(published) == 1
    row = published.iloc[0]
    assert row["methodology_version"] == METHODOLOGY_VERSION
    assert row["season"] == (2026 if populated else 0)
    float_columns = (
        [
            "best_old_extrapolation_laps",
            "best_new_extrapolation_laps",
            "actual_old_extrapolation_laps",
            "actual_new_extrapolation_laps",
        ]
        if summary
        else ["old_extrapolation_laps", "new_extrapolation_laps"]
    )
    for column in float_columns:
        assert str(published[column].dtype) == "float64"
    if populated:
        for column, value in values.items():
            assert row[column] == value
    else:
        assert published[float_columns].isna().all().all()
        if summary:
            assert row["bootstrap_valid_samples"] == 0
            assert not row["boundary_minimum"]
