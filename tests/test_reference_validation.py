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


def test_race_control_report_binds_official_boundary_annotations() -> None:
    root = Path(__file__).parents[1] / "validation"
    content = (root / "race-control-probes-v1.json").read_text(encoding="utf-8").encode("utf-8")
    reference = json.loads(content)
    report = json.loads((root / "race-control-results-v1.json").read_text())

    assert report["reference_sha256"] == hashlib.sha256(content).hexdigest()
    assert {case["id"] for case in report["cases"]} == {case["id"] for case in reference["cases"]}
    assert report["exact_positive_matches"] == 15
    assert report["population_precision"] is None
    assert reference["sources"]["madrid_report"]["url"].startswith("https://www.formula1.com/")
    assert reference["sources"]["madrid_pits"]["url"].endswith("pit-stop-summary")


@pytest.mark.parametrize(
    "kind,column",
    [
        ("race_control_start", "deployment_lap"),
        ("race_control_end", "end_lap"),
        ("race_control_finish", "end_lap"),
    ],
)
def test_control_probes_require_source_coverage(kind: str, column: str) -> None:
    c, ref = fixture()
    c.execute("create schema staging")
    c.execute("create table staging.stg_race_control(season int, round int, session varchar)")
    c.execute("""create table marts.race_control_events(season int, round int,
        event_type varchar, deployment_lap int, end_lap int, event_status varchar)""")
    ref["cases"][0].update(kind=kind, other="VSC")
    # An event row alone does not establish source coverage.
    c.execute("insert into marts.race_control_events values (2025,13,'VSC',5,5,'finished')")
    assert evaluate(c, ref)["counts"]["uncovered"] == 1
    c.execute("insert into staging.stg_race_control values (2025,13,'R')")
    assert evaluate(c, ref)["counts"]["true_positive"] == 1
    c.execute(f"update marts.race_control_events set {column}=20")
    assert evaluate(c, ref)["counts"]["false_negative"] == 1
    ref["cases"][0]["expected"] = False
    with pytest.raises(ValueError, match="positive"):
        evaluate(c, ref)


def test_v2_stratified_report_tracks_binary_categorical_and_expected_limitations() -> None:
    c, ref = fixture()
    c.execute("create schema staging")
    c.execute("create table staging.stg_race_control(season int, round int, session varchar)")
    c.execute("""create table marts.race_control_events(season int, round int,
        event_number int, event_type varchar, deployment_lap int, end_lap int,
        event_status varchar)""")
    c.execute("""create table marts.race_control_impact(season int, round int,
        event_number int, driver_code varchar, position_before int, position_after int,
        position_evidence_class varchar, position_eligible boolean, pit_timing_class varchar,
        story_status varchar, story_direction varchar)""")
    c.execute("""create table marts.race_control_checkpoints(season int, round int,
        event_number int, driver_code varchar, checkpoint_type varchar, running_order int,
        evidence_class varchar, eligible boolean)""")
    c.execute("""create table marts.race_control_effects(season int, round int,
        event_number int, driver_code varchar, effect_type varchar, eligible boolean,
        lower_bound double, upper_bound double, exclusion_reason varchar)""")
    c.execute("insert into staging.stg_race_control values (2025,13,'R')")
    c.execute("insert into marts.race_control_events values (2025,13,1,'VSC',5,6,'complete')")
    c.execute("""insert into marts.race_control_impact values
        (2025,13,1,'PIA',2,2,'recorded',true,'no_stop_observed',
        'no_material_effect','neutral')""")
    ref.update(schema_version=2)
    ref["cases"] = [
        {
            **ref["cases"][0],
            "id": "boundary-positive",
            "kind": "race_control_start",
            "other": "VSC",
            "expected_state": "present",
            "coverage_expectation": "covered",
            "annotation_group": "boundary",
        },
        {
            **ref["cases"][0],
            "id": "story-match",
            "kind": "driver_story",
            "event_number": 1,
            "expected_state": "no_material_effect",
            "expected_direction": "neutral",
            "coverage_expectation": "covered",
            "annotation_group": "driver",
        },
        {
            **ref["cases"][0],
            "id": "expected-limitation",
            "kind": "pit_story",
            "driver": "NOR",
            "event_number": 1,
            "expected_state": "unavailable",
            "coverage_expectation": "source_limited",
            "annotation_group": "pit",
        },
    ]
    for case in ref["cases"]:
        case.pop("expected", None)
        case["evidence_note"] = "Synthetic test annotation."

    report = evaluate(c, ref)

    assert report["validation_pass"]
    assert report["counts"]["true_positive"] == 1
    assert report["counts"]["matched"] == 1
    assert report["counts"]["expected_unavailable"] == 1
    assert report["annotated_precision"] == 1.0
    assert report["annotated_positive_recall"] == 1.0


def test_v2_impact_position_applies_declared_tolerance_and_requires_evidence() -> None:
    c, ref = fixture()
    c.execute("""create table marts.race_control_impact(season int, round int,
        event_number int, driver_code varchar, position_before int, position_after int,
        position_evidence_class varchar, position_eligible boolean)""")
    c.execute("insert into marts.race_control_impact values (2025,13,1,'PIA',2,4,'recorded',true)")
    ref.update(schema_version=2)
    ref["cases"] = [
        {
            **ref["cases"][0],
            "kind": "impact_position",
            "event_number": 1,
            "expected_state": "recorded",
            "expected_position_before": 2,
            "expected_position_after": 3,
            "position_tolerance": 1,
            "coverage_expectation": "covered",
            "annotation_group": "driver",
            "evidence_note": "External completed-lap chart permits a one-place boundary offset.",
        }
    ]
    ref["cases"][0].pop("expected", None)

    assert evaluate(c, ref)["validation_pass"]
    ref["cases"][0]["evidence_note"] = ""
    with pytest.raises(ValueError, match="evidence metadata"):
        evaluate(c, ref)


def test_committed_race_control_v2_report_is_stratified_and_bound() -> None:
    root = Path(__file__).parents[1] / "validation"
    content = (root / "race-control-probes-v2.json").read_text(encoding="utf-8").encode("utf-8")
    reference = json.loads(content)
    report = json.loads((root / "race-control-results-v2.json").read_text())

    assert report["reference_sha256"] == hashlib.sha256(content).hexdigest()
    assert len(reference["cases"]) == 36
    assert {
        group: sum(case["annotation_group"] == group for case in reference["cases"])
        for group in ("boundary", "driver", "pit")
    } == {
        "boundary": 18,
        "driver": 12,
        "pit": 6,
    }
    assert report["validation_pass"]
    assert report["population_precision"] is None
