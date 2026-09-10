from pathlib import Path

import duckdb
import pandas as pd
import pytest
from analytics.traffic import (
    _LAP_REQUIRED,
    _REPLAY_REQUIRED,
    _SUMMARY_COLUMNS,
    analyse_traffic_adjusted_pace,
)

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
    assert "where clean_air_eligible and traffic_adjusted_pace_delta_sec is not null" in page
    assert (
        "where traffic_association_eligible and traffic_associated_delta_sec_per_lap is not null"
        in page
    )
    assert "not a confidence interval" in page
    assert "heuristic sample-strength" in page
    assert "id=confidence" not in page
    assert "id=clean_air_confidence" in page
    assert "id=traffic_association_confidence" in page


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


@pytest.mark.parametrize("populated", [False, True])
def test_traffic_source_preserves_metric_evidence_and_sentinel_types(populated: bool) -> None:
    text_columns = {
        "race_name",
        "driver_code",
        "team",
        "confidence",
        "clean_air_confidence",
        "traffic_association_confidence",
        "methodology_version",
    }
    bool_columns = {"clean_air_eligible", "traffic_association_eligible"}
    row: dict[str, object] = {
        column: "test" if column in text_columns else False if column in bool_columns else 1.0
        for column in _SUMMARY_COLUMNS
    }
    row.update(
        season=2026,
        round=1,
        clean_air_eligible=True,
        clean_air_confidence="medium",
        traffic_association_eligible=False,
        traffic_association_confidence="insufficient",
        confidence="insufficient",
        methodology_version="traffic-v3-metric-evidence",
    )
    frame = pd.DataFrame([row])
    with duckdb.connect() as connection:
        connection.execute("create schema marts")
        connection.register("fixture", frame)
        connection.execute("create table marts.traffic_adjusted_pace as select * from fixture")
        if not populated:
            connection.execute("delete from marts.traffic_adjusted_pace")
        result = connection.execute(PACE_SOURCE.read_text(encoding="utf-8")).df()
    assert len(result) == 1
    output = result.iloc[0]
    assert output["methodology_version"] == "traffic-v3-metric-evidence"
    assert bool(output["clean_air_eligible"]) == populated
    assert not output["traffic_association_eligible"]
    assert output["clean_air_confidence"] == ("medium" if populated else "unavailable")
    assert output["traffic_association_confidence"] == (
        "insufficient" if populated else "unavailable"
    )
    assert str(result["clean_air_eligible"].dtype) == "bool"
    assert str(result["traffic_association_eligible"].dtype) == "bool"


def test_actual_empty_traffic_summary_materializes_boolean_eligibility() -> None:
    summary = analyse_traffic_adjusted_pace(
        pd.DataFrame(columns=sorted(_LAP_REQUIRED)),
        pd.DataFrame(columns=sorted(_REPLAY_REQUIRED)),
    ).summary
    assert summary.empty
    with duckdb.connect() as connection:
        connection.execute("create schema marts")
        connection.register("empty_summary", summary)
        connection.execute(
            "create table marts.traffic_adjusted_pace as select * from empty_summary"
        )
        types = dict(
            connection.execute(
                "select column_name, data_type from information_schema.columns "
                "where table_schema = 'marts' and table_name = 'traffic_adjusted_pace'"
            ).fetchall()
        )
        result = connection.execute(PACE_SOURCE.read_text(encoding="utf-8")).df()
    for field in ("clean_air_eligible", "traffic_association_eligible"):
        assert str(summary[field].dtype) == "bool"
        assert types[field] == "BOOLEAN"
        assert str(result[field].dtype) == "bool"
        assert not result.iloc[0][field]
    assert result["season"].tolist() == [0]
