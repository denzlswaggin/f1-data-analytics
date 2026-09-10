from pathlib import Path

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
