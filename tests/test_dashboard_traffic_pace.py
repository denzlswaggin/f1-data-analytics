from pathlib import Path


ROOT = Path(__file__).parents[1]
PAGE = ROOT / "dashboard" / "pages" / "traffic-adjusted-pace.md"
PACE_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "traffic_adjusted_pace.sql"
LAPS_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "traffic_adjusted_laps.sql"
COVERAGE_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "data_coverage.sql"


def test_traffic_page_exposes_rank_association_and_lap_evidence() -> None:
    page = PAGE.read_text(encoding="utf-8")

    assert "traffic_adjusted_pace_delta_sec" in page
    assert "traffic_associated_delta_sec_per_lap" in page
    assert "traffic_associated_p25_sec" in page
    assert "traffic_associated_p75_sec" in page
    assert "traffic_exposure_pct" in page
    assert "replay_coverage_pct" in page
    assert "f1.traffic_adjusted_laps" in page
    assert "not proof that dirty air caused" in page
    assert "five clean laps" in page


def test_traffic_sources_publish_the_method_evidence() -> None:
    pace = PACE_SOURCE.read_text(encoding="utf-8")
    laps = LAPS_SOURCE.read_text(encoding="utf-8")
    coverage = COVERAGE_SOURCE.read_text(encoding="utf-8")

    assert "from marts.traffic_adjusted_pace" in pace
    assert "methodology_version" in pace
    assert "matched_traffic_laps" in pace
    assert "from marts.traffic_adjusted_laps" in laps
    assert "paired_traffic_delta_sec" in laps
    assert "'traffic_pace'" in coverage
