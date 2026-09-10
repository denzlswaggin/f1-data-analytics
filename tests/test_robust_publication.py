"""Independent reconstruction and policy-grid regression checks."""

from __future__ import annotations

import runpy
from pathlib import Path

import duckdb
import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _seed(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute("create schema marts")
    connection.execute("""create table marts.traffic_adjusted_laps as
        select 2025 as season, 1 as round, 10 as lap_number, 'MEDIUM' as compound,
            3 as peer_count, * from (values
                ('A', 90.0, 101.0, -11.0), ('B', 100.0, 101.0, -1.0),
                ('C', 101.0, 100.0, 1.0), ('D', 200.0, 100.0, 100.0)
            ) t(driver_code, lap_time_sec, peer_lap_median_sec, controlled_pace_delta_sec)""")
    connection.execute("""create table marts.pit_timing_scenarios as
        select 2025 as season, 1 as round, 'A' as driver_code, 1 as stop_number,
            shift as shift_laps, shift < 3 as supported,
            case when shift < 3 then shift::double end as estimated_cost_index_sec,
            case when shift < 3 then shift::double end as delta_vs_actual_sec,
            case when shift < 3 then -shift::double end as estimated_gain_vs_actual_sec,
            case when shift < 3 then shift::double end as delta_p25_sec,
            case when shift < 3 then shift::double end as delta_p75_sec,
            greatest(0, shift + 2)::double as old_extrapolation_laps,
            0.0 as new_extrapolation_laps,
            case when shift < 3 then '' else 'old_extrapolation_limit' end as exclusion_reason
        from range(-3, 4) t(shift)""")
    connection.execute("""create table marts.pit_timing_sensitivity as
        select 2025 as season, 1 as round, 'A' as driver_code, 1 as stop_number,
            true as eligible, 6 as supported_scenarios, -3 as best_supported_shift_laps,
            3.0 as estimated_gain_vs_actual_sec, true as boundary_minimum,
            300 as bootstrap_requested_samples, 300 as bootstrap_valid_samples,
            310 as bootstrap_attempted_samples, 100.0 as best_shift_win_pct,
            'medium' as confidence""")


@pytest.mark.parametrize(
    "mutation",
    [
        "",
        "update marts.traffic_adjusted_laps set peer_count = 2",
        "update marts.traffic_adjusted_laps set peer_lap_median_sec = 150",
        "update marts.traffic_adjusted_laps set controlled_pace_delta_sec = 0",
        "update marts.pit_timing_scenarios set delta_vs_actual_sec = 0 where not supported",
        "update marts.pit_timing_scenarios set old_extrapolation_laps = 5 where shift_laps = 0",
        "update marts.pit_timing_sensitivity set bootstrap_valid_samples = 99",
        "update marts.pit_timing_sensitivity set bootstrap_valid_samples = 269",
        "update marts.pit_timing_sensitivity set confidence = 'high'",
        "update marts.pit_timing_sensitivity set boundary_minimum = false",
        "update marts.pit_timing_sensitivity set supported_scenarios = 7",
    ],
)
def test_reconstructs_peers_and_checks_model_publication(mutation: str) -> None:
    checker = runpy.run_path(str(SCRIPTS / "check_robust_estimates.py"))["check"]
    with duckdb.connect() as connection:
        _seed(connection)
        if mutation:
            connection.execute(mutation)
        violations = checker(connection)
    assert any(violations.values()) == bool(mutation)


def test_pit_grid_requires_actual_baseline_and_an_alternative() -> None:
    grid = runpy.run_path(str(SCRIPTS / "report_robustness_sensitivity.py"))["pit_grid"]
    scenarios = pd.DataFrame(
        {
            "season": [2025] * 3,
            "round": [1] * 3,
            "driver_code": ["A"] * 3,
            "stop_number": [1] * 3,
            "shift_laps": [-1, 0, 1],
            "old_extrapolation_laps": [0.0, 3.0, 5.0],
            "new_extrapolation_laps": [1.0, 0.0, 0.0],
        }
    )
    result = grid(scenarios)
    assert len(result) == 9
    assert result[0]["fitted_stops_with_comparison"] == 0
    assert result[3]["fitted_stops_with_comparison"] == 0  # actual only
    assert result[4]["bounded_scenarios_including_actual"] == 2
    assert result[7]["bounded_scenarios_including_actual"] == 3


def test_traffic_grid_changes_cohort_and_publication_thresholds_separately() -> None:
    grid = runpy.run_path(str(SCRIPTS / "report_robustness_sensitivity.py"))["traffic_grid"]
    laps = pd.DataFrame(
        [
            {
                "season": 2025,
                "round": 1,
                "race_name": "Test",
                "driver_code": driver,
                "team": driver,
                "lap_number": lap,
                "compound": "MEDIUM",
                "lap_time_sec": 100.0,
                "tyre_life": lap,
                "air_state": "clean_air",
                "valid_context_samples": 100,
                "traffic_samples": 0,
                "replay_coverage_pct": 100.0,
            }
            for lap in range(2, 10)
            for driver in ("A", "B", "C", "D")
        ]
    )
    result = grid(laps)
    assert len(result) == 9
    assert [row["clean_air_results"] for row in result] == [4, 4, 0, 4, 4, 0, 0, 0, 0]
    assert all(row["association_results"] == 0 for row in result)
    assert result[3]["evidence_laps"] == 32
