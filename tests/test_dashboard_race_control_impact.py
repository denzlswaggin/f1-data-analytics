from pathlib import Path

ROOT = Path(__file__).parents[1]
PAGE = ROOT / "dashboard" / "pages" / "race-control-impact.md"
EVENT_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "race_control_events.sql"
IMPACT_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "race_control_impact.sql"
COVERAGE = ROOT / "dashboard" / "sources" / "f1" / "data_coverage.sql"


def test_page_exposes_position_time_pit_and_exclusion_evidence() -> None:
    page = PAGE.read_text(encoding="utf-8")

    assert "positions_gained" in page
    assert "field_adjusted_gap_gain_s" in page
    assert "pitted_during_intervention" in page
    assert "lap deficit changed" in page.lower()
    assert "rather than what race control caused" in page
    assert "at least 12 cars" in page


def test_sources_publish_both_marts_with_empty_sentinels() -> None:
    events = EVENT_SOURCE.read_text(encoding="utf-8")
    impact = IMPACT_SOURCE.read_text(encoding="utf-8")
    coverage = COVERAGE.read_text(encoding="utf-8")

    assert "from marts.race_control_events" in events
    assert "where not exists" in events
    assert "from marts.race_control_impact" in impact
    assert "where not exists" in impact
    assert "methodology_version" in events
    assert "field_adjusted_gap_gain_s" in impact
    assert "'race_control'" in coverage
