"""Publication checks reconcile summary semantics with underlying lap evidence."""

from __future__ import annotations

import runpy
from pathlib import Path

import duckdb
import pytest


def _seed(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute("create schema marts")
    connection.execute("""create table marts.traffic_adjusted_laps as
        select 100 as context_samples, 100 as valid_context_samples, 0 as traffic_samples,
            4.0::double as median_gap_to_ahead_s, 'MEDIUM' as compound,
            'clean_air' as air_state, 100.0 as replay_coverage_pct""")
    connection.execute("""create table marts.traffic_adjusted_pace as
        select 8 as clean_air_laps, 0 as matched_traffic_laps,
            true as clean_air_eligible, false as traffic_association_eligible,
            -0.1 as traffic_adjusted_pace_delta_sec,
            null::double as traffic_associated_delta_sec_per_lap,
            'medium' as clean_air_confidence,
            'insufficient' as traffic_association_confidence, 'insufficient' as confidence""")
    connection.execute("""create table marts.tyre_warmup as
        select 2025 as season, 4 as round, 2 as stint, * from (values
            ('A', 4, 4, true, true, false, true, true, true, 'observed_complete'),
            ('B', null, 6, false, true, false, false, true, false, 'observed_incomplete'),
            ('C', null, null, false, false, true, true, true, true, 'right_censored'),
            ('D', null, null, false, false, false, false, true, false, 'incomplete'),
            ('E', null, null, false, false, false, false, false, false, 'unavailable')
        ) t(driver_code, time_to_pace_laps, first_observed_confirmation_laps,
            confirmation_history_complete, stable_pace_achieved, right_censored,
            observation_complete, warmup_eligible, crossover_eligible, settling_status)""")
    connection.execute("""create table marts.tyre_warmup_laps as
        select season, round, driver_code, stint, offset_lap as post_stop_offset,
            true as lap_eligible,
            (driver_code = 'A' and offset_lap in (3, 4))
                or (driver_code = 'B' and offset_lap in (5, 6)) as within_stable_band
        from marts.tyre_warmup cross join range(1, 7) t(offset_lap)
        where warmup_eligible and (driver_code in ('A', 'C') or offset_lap != 2)""")


@pytest.mark.parametrize(
    "mutation",
    [
        "",
        "update marts.traffic_adjusted_laps set valid_context_samples = 10",
        "update marts.traffic_adjusted_laps set traffic_samples = 101",
        "update marts.traffic_adjusted_laps set median_gap_to_ahead_s = 'Infinity'::double",
        "update marts.traffic_adjusted_laps set compound = 'None'",
        "update marts.traffic_adjusted_pace set clean_air_confidence = 'insufficient'",
        "update marts.traffic_adjusted_pace set traffic_association_eligible = true",
        "update marts.traffic_adjusted_pace set traffic_adjusted_pace_delta_sec = null",
        "update marts.tyre_warmup set time_to_pace_laps = 6 where driver_code = 'B'",
        "update marts.tyre_warmup set settling_status = 'observed_complete' where driver_code = 'B'",
        "update marts.tyre_warmup set confirmation_history_complete = true where driver_code = 'B'",
        "update marts.tyre_warmup set right_censored = true where driver_code = 'D'",
        "delete from marts.tyre_warmup_laps where driver_code = 'A' and post_stop_offset = 1",
        "update marts.tyre_warmup_laps set within_stable_band = false where driver_code = 'A'",
    ],
)
def test_metric_publication_detects_inconsistent_evidence(mutation: str) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts/check_metric_evidence.py"
    checker = runpy.run_path(str(script))["check"]
    with duckdb.connect() as connection:
        _seed(connection)
        if mutation:
            connection.execute(mutation)
        violations = checker(connection)
    assert any(violations.values()) == bool(mutation)
