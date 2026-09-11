from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import duckdb
import pytest
from scripts.report_reference_validation import evaluate


def fixture() -> tuple[duckdb.DuckDBPyConnection, dict[str, Any]]:
    c = duckdb.connect()
    c.execute("create schema marts")
    c.execute("""create table marts.pit_lap_context(season int, round int,
        driver_code varchar, lap_number int, is_pit_in_lap boolean)""")
    c.execute("""create table marts.race_replay(season int, round int,
        driver_code varchar, t_s double, lap_number int)""")
    c.execute("""create table marts.race_overtakes(season int, round int,
        t_s double, passer_code varchar, passed_code varchar)""")
    c.execute("""create table marts.racecraft_battles(season int, round int,
        attacker_code varchar, defender_code varchar, pass_lap int,
        converted boolean, eligible boolean)""")
    ref = {
        "schema_version": 1,
        "lap_tolerance": 1,
        "sources": {"f1": {}},
        "cases": [
            {
                "id": "case",
                "season": 2025,
                "round": 13,
                "driver": "PIA",
                "other": "NOR",
                "kind": "overtake",
                "lap_min": 5,
                "lap_max": 5,
                "expected": True,
                "source_id": "f1",
            }
        ],
    }
    c.execute("insert into marts.race_replay values (2025,13,'PIA',100,4),(2025,13,'PIA',101,5)")
    return c, ref


@pytest.mark.parametrize("expected,outcome", [(True, "false_negative"), (False, "true_negative")])
def test_absence_with_coverage(expected: bool, outcome: str) -> None:
    c, ref = fixture()
    ref["cases"][0]["expected"] = expected
    report = evaluate(c, ref)
    assert report["counts"][outcome] == 1
    assert report["population_precision"] is None


def test_exact_and_tolerant_are_separate() -> None:
    c, ref = fixture()
    c.execute("insert into marts.race_overtakes values (2025,13,100,'PIA','NOR')")
    row = evaluate(c, ref)["cases"][0]
    assert row["tolerant_match"] and not row["exact_match"]
    ref["lap_tolerance"] = 0
    assert evaluate(c, ref)["counts"]["false_negative"] == 1


def test_negative_windows_not_expanded() -> None:
    c, ref = fixture()
    ref["cases"][0]["expected"] = False
    c.execute("insert into marts.race_overtakes values (2025,13,100,'PIA','NOR')")
    assert evaluate(c, ref)["counts"]["true_negative"] == 1
    c.execute("insert into marts.race_overtakes values (2025,13,101,'PIA','NOR')")
    assert evaluate(c, ref)["counts"]["false_positive"] == 1


def test_missing_coverage_is_not_success_or_miss() -> None:
    c, ref = fixture()
    c.execute("delete from marts.race_replay")
    report = evaluate(c, ref)
    assert report["counts"]["uncovered"] == 1
    assert report["annotated_positive_recall"] is None


def test_far_tick_and_wrong_pair_do_not_match() -> None:
    c, ref = fixture()
    c.execute(
        "insert into marts.race_overtakes values (2025,13,200,'PIA','NOR'),(2025,13,101,'NOR','PIA')"
    )
    assert evaluate(c, ref)["counts"]["false_negative"] == 1


def test_pit_requires_entry_not_just_context_row() -> None:
    c, ref = fixture()
    ref["cases"][0]["kind"] = "pit_entry"
    c.execute("insert into marts.pit_lap_context values (2025,13,'PIA',5,false)")
    assert evaluate(c, ref)["counts"]["false_negative"] == 1
    c.execute("update marts.pit_lap_context set is_pit_in_lap=true")
    assert evaluate(c, ref)["counts"]["true_positive"] == 1


def test_competitive_requires_eligible_conversion() -> None:
    c, ref = fixture()
    ref["cases"][0].update(kind="competitive_conversion", expected=False)
    c.execute("insert into marts.racecraft_battles values (2025,13,'PIA','NOR',5,true,false)")
    assert evaluate(c, ref)["counts"]["true_negative"] == 1
    c.execute("update marts.racecraft_battles set eligible=true")
    assert evaluate(c, ref)["counts"]["false_positive"] == 1


def test_duplicate_cases_rejected() -> None:
    c, ref = fixture()
    ref["cases"].append(copy.deepcopy(ref["cases"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        evaluate(c, ref)


@pytest.mark.parametrize("value", [-1, True, 1.5])
def test_invalid_tolerance_rejected(value: Any) -> None:
    c, ref = fixture()
    ref["lap_tolerance"] = value
    with pytest.raises(ValueError, match="lap_tolerance"):
        evaluate(c, ref)


def test_committed_report_binds_frozen_annotations() -> None:
    root = Path(__file__).parents[1] / "validation"
    content = (root / "reference-events-v1.json").read_text(encoding="utf-8").encode("utf-8")
    report = json.loads((root / "reference-results-v1.json").read_text())
    assert report["reference_sha256"] == hashlib.sha256(content).hexdigest()
    reference = json.loads(content)
    assert {c["id"] for c in report["cases"]} == {c["id"] for c in reference["cases"]}
    assert report["exact_positive_matches"] == 13
    assert report["population_precision"] is None


@pytest.mark.parametrize(
    "kind,column", [("race_control_start", "deployment_lap"), ("race_control_end", "end_lap")]
)
def test_control_probes_require_source_coverage(kind: str, column: str) -> None:
    c, ref = fixture()
    c.execute("create schema staging")
    c.execute("create table staging.stg_race_control(season int, round int, session varchar)")
    c.execute("""create table marts.race_control_events(season int, round int,
        event_type varchar, deployment_lap int, end_lap int)""")
    ref["cases"][0].update(kind=kind, other="VSC")
    # An event row alone does not establish source coverage.
    c.execute("insert into marts.race_control_events values (2025,13,'VSC',5,5)")
    assert evaluate(c, ref)["counts"]["uncovered"] == 1
    c.execute("insert into staging.stg_race_control values (2025,13,'R')")
    assert evaluate(c, ref)["counts"]["true_positive"] == 1
    c.execute(f"update marts.race_control_events set {column}=20")
    assert evaluate(c, ref)["counts"]["false_negative"] == 1
    ref["cases"][0]["expected"] = False
    with pytest.raises(ValueError, match="positive"):
        evaluate(c, ref)
