from __future__ import annotations

import copy
from typing import Any

import duckdb
import pytest
from scripts.report_pass_windows import evaluate


def fixture() -> tuple[duckdb.DuckDBPyConnection, dict[str, Any]]:
    c = duckdb.connect()
    c.execute("create schema marts")
    c.execute(
        "create table marts.race_replay(season int, round int, driver_code varchar, t_s double, lap_number int)"
    )
    c.execute(
        "create table marts.race_overtakes(season int, round int, t_s double, passer_code varchar, passed_code varchar)"
    )
    c.executemany(
        "insert into marts.race_replay values (2025,1,?,?,1)",
        [(driver, t) for driver in ["AAA", "BBB"] for t in range(10)],
    )
    ref = {
        "schema_version": 1,
        "lap_tolerance": 0,
        "windows": [
            {
                "id": "pair",
                "season": 2025,
                "round": 1,
                "pair": ["AAA", "BBB"],
                "anchor_driver": "AAA",
                "lap_min": 1,
                "lap_max": 1,
                "completeness": "provisional",
                "source_url": "https://example.com/report",
                "expected": [
                    {"passer_code": "BBB", "passed_code": "AAA", "lap_number": 1},
                    {"passer_code": "AAA", "passed_code": "BBB", "lap_number": 1},
                ],
            }
        ],
    }
    return c, ref


def test_exact_reversal_sequence_and_no_precision_claim() -> None:
    c, ref = fixture()
    c.execute(
        "insert into marts.race_overtakes values (2025,1,3,'BBB','AAA'),(2025,1,7,'AAA','BBB')"
    )
    result = evaluate(c, ref)
    row = result["windows"][0]
    assert result["covered_windows"] == 1
    assert len(row["matching"]["matches"]) == 2
    assert row["precision"] is None and row["false_positive_count"] is None


def test_missing_partner_unscored_even_when_anchor_present() -> None:
    c, ref = fixture()
    c.execute("delete from marts.race_replay where driver_code='BBB'")
    row = evaluate(c, ref)["windows"][0]
    assert not row["covered"] and row["matching"] is None


def test_partner_gap_not_bridged() -> None:
    c, ref = fixture()
    c.execute("delete from marts.race_replay where driver_code='BBB' and t_s between 3 and 7")
    row = evaluate(c, ref)["windows"][0]
    assert not row["covered"]
    assert row["coverage"]["BBB"]["max_gap_s"] == 6


def test_missing_anchor_lap_is_not_a_negative_result() -> None:
    c, ref = fixture()
    ref["windows"][0]["lap_max"] = 2
    row = evaluate(c, ref)["windows"][0]
    assert row["missing_anchor_laps"] == [2] and row["matching"] is None


def test_extra_detections_require_review_not_false_positive_label() -> None:
    c, ref = fixture()
    ref["windows"][0]["expected"] = []
    c.execute("insert into marts.race_overtakes values (2025,1,3,'BBB','AAA')")
    row = evaluate(c, ref)["windows"][0]
    assert row["matching"]["unmatched_observed_indices"] == [0]
    assert row["false_positive_count"] is None


def test_simultaneous_directions_are_ambiguous() -> None:
    c, ref = fixture()
    c.execute(
        "insert into marts.race_overtakes values (2025,1,3,'BBB','AAA'),(2025,1,3,'AAA','BBB')"
    )
    row = evaluate(c, ref)["windows"][0]
    assert not row["covered"] and "ambiguous_simultaneous_pair_events" in row["unscored_reasons"]


def test_unknown_lap_is_not_silent_coverage() -> None:
    c, ref = fixture()
    c.execute("update marts.race_replay set lap_number=null where driver_code='BBB' and t_s=3")
    assert not evaluate(c, ref)["windows"][0]["covered"]


def test_other_pair_and_outside_window_excluded() -> None:
    c, ref = fixture()
    c.execute(
        "insert into marts.race_overtakes values (2025,1,3,'BBB','CCC'),(2025,1,20,'AAA','BBB')"
    )
    assert evaluate(c, ref)["windows"][0]["observed"] == []


@pytest.mark.parametrize(
    "change",
    [{"completeness": "adjudicated"}, {"anchor_driver": "CCC"}, {"lap_min": True}, {"lap_max": 0}],
)
def test_invalid_window_rejected(change: dict[str, Any]) -> None:
    c, ref = fixture()
    ref["windows"][0].update(change)
    with pytest.raises(ValueError):
        evaluate(c, ref)


def test_overlap_rejected() -> None:
    c, ref = fixture()
    second = copy.deepcopy(ref["windows"][0])
    second["id"] = "other"
    ref["windows"].append(second)
    with pytest.raises(ValueError, match="Overlapping"):
        evaluate(c, ref)
