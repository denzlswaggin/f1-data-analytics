from pathlib import Path

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
