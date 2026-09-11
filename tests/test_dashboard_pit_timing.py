import re
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


def test_stop_picker_includes_excluded_stops_and_uses_integer_labels() -> None:
    page = PAGE.read_text(encoding="utf-8")
    result = _empty_result()
    with duckdb.connect() as connection:
        connection.execute("create schema f1")
        connection.register("contract", result.summary)
        connection.execute("create table f1.pit_timing_sensitivity as select * from contract")
        connection.execute("""insert into f1.pit_timing_sensitivity
            (season, round, driver_code, stop_number, actual_pit_lap, eligible) values
            (2026, 1, 'AAA', 1, 8, false), (2026, 1, 'BBB', 2, 10, true),
            (2026, 2, 'CCC', 1, 5, true)""")
        for name in ("race_stops", "stop_choices"):
            match = re.search(rf"```sql {name}\n(.*?)\n```", page, re.S)
            assert match is not None
            query = (
                match[1]
                .replace("${inputs.season.value}", "2026")
                .replace("${inputs.race.value}", "1")
                .replace("${race_stops}", "race_stops")
            )
            connection.execute(f"create table {name} as {query}")
        rows = connection.execute("select stop_label, choice_label from stop_choices").fetchall()
    assert rows == [
        ("AAA · Stop 1", "AAA · Stop 1 · Excluded"),
        ("BBB · Stop 2", "BBB · Stop 2 · Supported"),
    ]


def test_race_catalog_separates_missing_inputs_from_model_exclusions() -> None:
    with duckdb.connect() as connection:
        connection.execute("""
            create schema staging; create schema marts;
            create table staging.stg_results as select * from (values
                (2024, 1), (2024, 1), (2024, 2), (2026, 1), (2023, 1)
            ) t(season, round);
            create table staging.stg_races as select * from (values
                (2024, 1, 'A', date '2024-03-01'),
                (2024, 2, 'B', date '2024-03-08'),
                (2026, 1, 'C', date '2026-03-01'),
                (2026, 23, 'Future', date '2026-12-01'),
                (2023, 1, 'Old', date '2023-03-01')
            ) t(season, round, race_name, race_date);
            create table marts.pit_timing_sensitivity as select * from (values
                (2024, 1, 'AAA', true), (2024, 1, 'AAA', false),
                (2024, 2, 'BBB', false)
            ) t(season, round, driver_code, eligible);
            create table staging.stg_laps as select * from (values
                (2024, 1, 'R'), (2024, 2, 'R'), (2026, 1, 'Q')
            ) t(season, round, session);
            create table marts.race_replay as select 2024 as season, 1 as round;
        """)
        rows = connection.execute(
            (SUMMARY_SOURCE.parent / "pit_timing_races.sql").read_text(encoding="utf-8")
        ).fetchdf()
    assert rows[["season", "round"]].values.tolist() == [[2024, 1], [2024, 2], [2026, 1]]
    assert rows["observed_stops"].tolist() == [2, 1, 0]
    assert rows["eligible_stops"].tolist() == [1, 0, 0]
    assert rows["drivers"].tolist() == [1, 1, 0]
    assert rows["lap_rows"].tolist() == [1, 1, 0]
    assert rows["replay_rows"].tolist() == [1, 0, 0]


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
