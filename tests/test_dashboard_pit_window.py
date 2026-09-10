from pathlib import Path

ROOT = Path(__file__).parents[1]
PAGE = ROOT / "dashboard" / "pages" / "pit-window-effectiveness.md"
SOURCE = ROOT / "dashboard" / "sources" / "f1" / "pit_window_effectiveness.sql"
COVERAGE = ROOT / "dashboard" / "sources" / "f1" / "data_coverage.sql"


def test_page_exposes_pairwise_swing_decomposition_and_exclusions() -> None:
    page = PAGE.read_text(encoding="utf-8")

    assert "net_time_gain_sec" in page
    assert "stop_duration_delta_sec" in page
    assert "on_track_gain_sec" in page
    assert "position_flip" in page
    assert "exclusion_reason" in page
    assert "not proof that strategy alone caused" in page
    assert "one to three laps apart" in page


def test_source_and_coverage_publish_pit_window_evidence() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    coverage = COVERAGE.read_text(encoding="utf-8")

    assert "from marts.pit_window_effectiveness" in source
    assert "methodology_version" in source
    assert "opportunity_type" in source
    assert "where not exists" in source
    assert "'pit_window'" in coverage
