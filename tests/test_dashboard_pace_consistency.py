from pathlib import Path

ROOT = Path(__file__).parents[1]
PAGE = ROOT / "dashboard" / "pages" / "pace-consistency.md"
SUMMARY_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "pace_consistency.sql"
LAPS_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "pace_consistency_laps.sql"
COVERAGE_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "data_coverage.sql"
NAV = ROOT / "dashboard" / "components" / "AppNav.svelte"


def test_page_exposes_consistency_tail_and_lap_evidence() -> None:
    page = PAGE.read_text(encoding="utf-8")

    assert "robust_consistency_sec" in page
    assert "slow_lap_cost_per_10_laps_sec" in page
    assert "f1.pace_consistency_laps" in page
    assert "Theil" in page
    assert "not labelled as driver errors" in page
    assert "Confidence depends only on sample" in page
    assert "eight modelled laps" in page


def test_sources_publish_summary_evidence_and_typed_sentinels() -> None:
    summary = SUMMARY_SOURCE.read_text(encoding="utf-8")
    laps = LAPS_SOURCE.read_text(encoding="utf-8")
    coverage = COVERAGE_SOURCE.read_text(encoding="utf-8")

    assert "from marts.pace_consistency" in summary
    assert "robust_consistency_pct" in summary
    assert "where not exists" in summary
    assert "from marts.pace_consistency_laps" in laps
    assert "pace_residual_sec" in laps
    assert "is_unexplained_slow_lap" in laps
    assert "'pace_consistency'" in coverage


def test_driver_navigation_links_to_consistency_page() -> None:
    navigation = NAV.read_text(encoding="utf-8")
    assert "{ label: 'Pace consistency', path: 'pace-consistency' }" in navigation
