from pathlib import Path

ROOT = Path(__file__).parents[1]
PAGE = ROOT / "dashboard" / "pages" / "racecraft-battles.md"
BATTLES_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "racecraft_battles.sql"
SUMMARY_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "racecraft_driver_summary.sql"
COVERAGE_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "data_coverage.sql"
NAV = ROOT / "dashboard" / "components" / "AppNav.svelte"


def test_page_keeps_attack_defence_and_uncertainty_separate() -> None:
    page = PAGE.read_text(encoding="utf-8")

    assert "attack_conversion_p05_pct" in page
    assert "defence_hold_p95_pct" in page
    assert "offense_eligible and defense_eligible" in page
    assert "does not combine" in page
    assert "Interrupted" in page
    assert "not a driver-skill score" in page
    assert "not official DRS" in page


def test_sources_publish_battles_summaries_and_empty_sentinels() -> None:
    battles = BATTLES_SOURCE.read_text(encoding="utf-8")
    summary = SUMMARY_SOURCE.read_text(encoding="utf-8")
    coverage = COVERAGE_SOURCE.read_text(encoding="utf-8")

    assert "from marts.racecraft_battles" in battles
    assert "where not exists" in battles
    assert "from marts.racecraft_driver_summary" in summary
    assert "where not exists" in summary
    assert "'racecraft'" in coverage


def test_driver_navigation_links_to_racecraft_page() -> None:
    navigation = NAV.read_text(encoding="utf-8")
    assert "{ label: 'Racecraft battles', path: 'racecraft-battles' }" in navigation


def test_page_distinguishes_continuous_evidence_and_reversal_ownership() -> None:
    page = PAGE.read_text(encoding="utf-8")
    for field in ("pressure_seconds", "longest_pressure_run_s", "release_run_s"):
        assert f"<Column id={field}" in page
    assert "Total pressure may" in page
    assert "eligibility uses the longest" in page
    assert "measured elapsed seconds" in page
    assert "missed expected replay sample" in page
    assert "defender receives the re-pass made" in page
    assert "attacker receives the re-pass" in page
    assert "quick_reversals_conceded" in page
