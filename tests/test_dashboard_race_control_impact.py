from pathlib import Path

import duckdb

ROOT = Path(__file__).parents[1]
PAGE = ROOT / "dashboard" / "pages" / "race-control-impact.md"
EVENT_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "race_control_events.sql"
IMPACT_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "race_control_impact.sql"
CHECKPOINT_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "race_control_checkpoints.sql"
EFFECT_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "race_control_effects.sql"
COVERAGE = ROOT / "dashboard" / "sources" / "f1" / "data_coverage.sql"
RACES_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "race_control_races.sql"


def test_page_exposes_driver_story_component_evidence_and_uncertainty() -> None:
    page = PAGE.read_text(encoding="utf-8")

    assert "positions_gained" in page
    assert "field_adjusted_gap_gain_s" in page
    assert "focus_driver_code" in page
    assert "pit_timing_class" in page
    assert "estimated_vsc_pit_saving" in page
    assert "lower_bound" in page and "upper_bound" in page
    assert "race_control_checkpoints" in page
    assert "race_control_effects" in page
    assert "facts kept distinct from counterfactual estimates" in page
    assert "never a claim that race control caused the final result" in page
    assert "Final result is context only" in page
    assert "finish_position" in page
    assert "five clean same-race green stops" in page
    assert "Official validation context — Madrid 2026" in page
    assert "pit-stop-summary" in page
    assert 'defaultValue={2026}' in page
    assert 'comparisonFmt="P0 after recovery"' not in page


def test_sources_publish_all_marts_with_empty_sentinels() -> None:
    events = EVENT_SOURCE.read_text(encoding="utf-8")
    impact = IMPACT_SOURCE.read_text(encoding="utf-8")
    checkpoints = CHECKPOINT_SOURCE.read_text(encoding="utf-8")
    effects = EFFECT_SOURCE.read_text(encoding="utf-8")
    coverage = COVERAGE.read_text(encoding="utf-8")

    assert "from marts.race_control_events" in events
    assert "where not exists" in events
    assert "from marts.race_control_impact" in impact
    assert "where not exists" in impact
    assert "methodology_version" in events
    assert "field_adjusted_gap_gain_s" in impact
    assert "from marts.race_control_checkpoints" in checkpoints
    assert "where not exists" in checkpoints
    assert "from marts.race_control_effects" in effects
    assert "where not exists" in effects
    assert "lower_bound" in effects
    assert "'race_control'" in coverage


def test_race_picker_keeps_no_event_and_missing_message_races() -> None:
    with duckdb.connect() as connection:
        connection.execute("create schema staging; create schema marts")
        connection.execute("""
            create table staging.stg_results as select * from (values
                (2024, 1), (2024, 1), (2024, 2), (2025, 1), (2026, 1), (2023, 1)
            ) t(season, round);
            create table staging.stg_races as select * from (values
                (2024, 1, 'Bahrain', date '2024-03-02'),
                (2024, 2, 'Saudi Arabia', date '2024-03-09'),
                (2025, 1, 'Australia', date '2025-03-16'),
                (2026, 1, 'Australia', date '2026-03-08'),
                (2026, 23, 'Future race', date '2026-12-06'),
                (2023, 1, 'Outside range', date '2023-03-05')
            ) t(season, round, race_name, race_date);
            create table staging.stg_race_control as select * from (values
                (2024, 1, 'R'), (2024, 2, 'R'), (2024, 2, 'R'),
                (2025, 1, 'Q'), (2026, 1, 'R')
            ) t(season, round, session);
            create table marts.race_control_events as select * from (values
                (2024, 2, true), (2026, 1, false)
            ) t(season, round, eligible)
        """)
        rows = connection.execute(RACES_SOURCE.read_text(encoding="utf-8")).df()
    assert rows[["season", "round"]].values.tolist() == [[2024, 1], [2024, 2], [2025, 1], [2026, 1]]
    assert rows["message_count"].tolist() == [1, 2, 0, 1]
    assert rows["event_count"].tolist() == [0, 1, 0, 1]
    assert rows["eligible_event_count"].tolist() == [0, 1, 0, 0]
