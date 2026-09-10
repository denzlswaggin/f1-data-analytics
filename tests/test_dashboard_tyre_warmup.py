from pathlib import Path

import duckdb
import pandas as pd
import pytest
from analytics.tyre_warmup import _empty_result

ROOT = Path(__file__).parents[1]
PAGE = ROOT / "dashboard" / "pages" / "tyre-warmup.md"
SUMMARY_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "tyre_warmup.sql"
LAPS_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "tyre_warmup_laps.sql"
COVERAGE_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "data_coverage.sql"


def test_page_exposes_settling_curve_outcomes_and_evidence() -> None:
    page = PAGE.read_text(encoding="utf-8")

    assert "first_flying_warmup_loss_sec" in page
    assert "time_to_pace_laps" in page
    assert "right_censored" in page
    assert "f1.tyre_warmup_laps" in page
    assert "Theil" in page
    assert "not tyre-temperature telemetry" in page
    assert "does not claim that one compound causally" in page
    assert page.count("where confirmation_history_complete and time_to_pace_laps is not null") == 2
    assert "first_observed_confirmation_laps" in page
    assert "right-censored bound" in page
    assert "Which stints took longest?" not in page
    assert "not calibrated probabilities" in page


def test_sources_publish_summary_lap_evidence_and_typed_sentinels() -> None:
    summary = SUMMARY_SOURCE.read_text(encoding="utf-8")
    laps = LAPS_SOURCE.read_text(encoding="utf-8")
    coverage = COVERAGE_SOURCE.read_text(encoding="utf-8")

    assert "from marts.tyre_warmup" in summary
    assert "baseline_mad_sec" in summary
    assert "where not exists" in summary
    assert "from marts.tyre_warmup_laps" in laps
    assert "expected_mature_delta_sec" in laps
    assert "used_for_baseline" in laps
    assert "'tyre_warmup'" in coverage


@pytest.mark.parametrize("populated", [False, True])
def test_summary_sql_preserves_observation_schema_and_typed_sentinel(populated: bool) -> None:
    frame = _empty_result().summary
    with duckdb.connect() as connection:
        connection.execute("create schema marts")
        connection.register("summary_input", frame)
        connection.execute("create table marts.tyre_warmup as select * from summary_input")
        if populated:
            connection.execute("""
                insert into marts.tyre_warmup
                    (season, round, driver_code, stint, time_to_pace_laps,
                     first_observed_confirmation_laps, confirmation_history_complete,
                     settling_status, methodology_version)
                values (2026, 1, 'AAA', 2, null, 4, false,
                        'observed_incomplete', 'tyre-warmup-v4-robust-peers')
                """)
        result = connection.execute(SUMMARY_SOURCE.read_text(encoding="utf-8")).fetchdf()
    assert len(result) == 1
    assert result.iloc[0]["season"] == (2026 if populated else 0)
    assert pd.isna(result.iloc[0]["time_to_pace_laps"])
    assert not bool(result.iloc[0]["confirmation_history_complete"])
    assert result.iloc[0]["methodology_version"] == "tyre-warmup-v4-robust-peers"
    assert pd.api.types.is_integer_dtype(result["first_observed_confirmation_laps"])
    if populated:
        assert result.iloc[0]["first_observed_confirmation_laps"] == 4
        assert result.iloc[0]["settling_status"] == "observed_incomplete"
    else:
        assert pd.isna(result.iloc[0]["first_observed_confirmation_laps"])
        assert result.iloc[0]["settling_status"] == "unavailable"
