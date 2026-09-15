"""Compare frozen external annotations with a snapshot; never infer truth from silence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import duckdb


def evaluate(connection: duckdb.DuckDBPyConnection, reference: dict[str, Any]) -> dict[str, Any]:
    cases = reference["cases"]
    schema_version = reference["schema_version"]
    if schema_version not in {1, 2} or len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Unsupported schema or duplicate annotation IDs")
    tolerance = reference["lap_tolerance"]
    if type(tolerance) is not int or tolerance < 0:
        raise ValueError("lap_tolerance must be a nonnegative integer")
    results = []
    for case in cases:
        if schema_version == 2:
            if (
                case.get("annotation_group") not in {"boundary", "driver", "pit"}
                or case.get("coverage_expectation") not in {"covered", "source_limited"}
                or not str(case.get("evidence_note", "")).strip()
            ):
                raise ValueError("Invalid v2 evidence metadata")
            for tolerance_name in ("lap_tolerance", "position_tolerance"):
                case_tolerance = case.get(tolerance_name, 0)
                if type(case_tolerance) is not int or case_tolerance < 0:
                    raise ValueError(f"{tolerance_name} must be a nonnegative integer")
        expected = (
            case.get("expected")
            if schema_version == 1
            else case.get("expected_state") in {"present", "detected"}
        )
        if (
            (schema_version == 1 and type(expected) is not bool)
            or (schema_version == 2 and not isinstance(case.get("expected_state"), str))
            or case["lap_min"] > case["lap_max"]
            or case["source_id"] not in reference["sources"]
        ):
            raise ValueError("Invalid reference annotation")
        params = [case["season"], case["round"], case["driver"]]
        low, high = case["lap_min"], case["lap_max"]
        kind = case["kind"]
        categorical_match: bool | None = None
        detected_state: str | None = None
        if kind == "pit_entry":
            coverage = connection.execute(
                """select count(distinct lap_number)
                from marts.pit_lap_context where season=? and round=? and driver_code=?
                and lap_number between ? and ?""",
                [*params, low, high],
            ).fetchone()
            detections = connection.execute(
                """select lap_number from marts.pit_lap_context
                where season=? and round=? and driver_code=? and is_pit_in_lap""",
                params,
            ).fetchall()
        elif kind in {"race_control_start", "race_control_end", "race_control_finish"}:
            if case["other"] not in {"Safety Car", "VSC", "Red Flag"}:
                raise ValueError("Unknown race-control event type")
            if schema_version == 1 and not expected:
                raise ValueError("Race-control probes currently support positive references only")
            # Coverage cannot be established from detected events themselves.
            # Require independent replay rows plus an available source-message partition.
            coverage = connection.execute(
                """select count(distinct lap_number) from marts.race_replay
                where season=? and round=? and driver_code=? and lap_number between ? and ?
                and exists (select 1 from staging.stg_race_control m
                    where m.season=? and m.round=? and m.session='R')""",
                [*params, low, high, case["season"], case["round"]],
            ).fetchone()
            column = "deployment_lap" if kind == "race_control_start" else "end_lap"
            status_filter = " and event_status='finished'" if kind == "race_control_finish" else ""
            detections = connection.execute(
                f"select {column} from marts.race_control_events "
                f"where season=? and round=? and event_type=?{status_filter}",
                [case["season"], case["round"], case["other"]],
            ).fetchall()
        elif kind in {"overtake", "competitive_conversion"}:
            coverage = connection.execute(
                """select count(distinct lap_number)
                from marts.race_replay where season=? and round=? and driver_code=?
                and lap_number between ? and ?""",
                [*params, low, high],
            ).fetchone()
            if kind == "overtake":
                # A pass timestamp has no lap column. Match its passer's nearest tick,
                # at most two seconds away; missing alignment is not a matched event.
                detections = connection.execute(
                    """select r.lap_number
                    from marts.race_overtakes e left join lateral (
                        select lap_number from marts.race_replay r
                        where r.season=e.season and r.round=e.round
                        and r.driver_code=e.passer_code and abs(r.t_s-e.t_s)<=2
                        order by abs(r.t_s-e.t_s), r.t_s limit 1
                    ) r on true
                    where e.season=? and e.round=? and e.passer_code=? and e.passed_code=?""",
                    [*params, case["other"]],
                ).fetchall()
            else:
                detections = connection.execute(
                    """select pass_lap from marts.racecraft_battles
                    where season=? and round=? and attacker_code=? and defender_code=?
                    and converted and eligible""",
                    [*params, case["other"]],
                ).fetchall()
        elif schema_version == 2 and kind in {
            "driver_checkpoint",
            "impact_position",
            "driver_story",
            "pit_story",
        }:
            event_number = int(case["event_number"])
            if kind == "driver_checkpoint":
                rows = connection.execute(
                    """select running_order, evidence_class, eligible
                    from marts.race_control_checkpoints
                    where season=? and round=? and event_number=? and driver_code=?
                    and checkpoint_type=?""",
                    [
                        case["season"],
                        case["round"],
                        event_number,
                        case["driver"],
                        case["checkpoint_type"],
                    ],
                ).fetchall()
                covered = bool(rows)
                if rows:
                    position, evidence_class, eligible = rows[0]
                    detected_state = str(evidence_class) if eligible else "unavailable"
                    position_ok = "expected_position" not in case or (
                        position is not None
                        and abs(int(position) - int(case["expected_position"]))
                        <= int(case.get("position_tolerance", 0))
                    )
                    categorical_match = detected_state == case["expected_state"] and position_ok
            elif kind == "impact_position":
                rows = connection.execute(
                    """select position_before, position_after, position_evidence_class,
                        position_eligible from marts.race_control_impact
                    where season=? and round=? and event_number=? and driver_code=?""",
                    [case["season"], case["round"], event_number, case["driver"]],
                ).fetchall()
                covered = bool(rows)
                if rows:
                    before, after, evidence_class, eligible = rows[0]
                    detected_state = str(evidence_class) if eligible else "unavailable"
                    position_tolerance = int(case.get("position_tolerance", 0))
                    position_match = all(
                        case.get(key) is None
                        or (
                            actual is not None
                            and abs(int(actual) - int(case[key])) <= position_tolerance
                        )
                        for key, actual in (
                            ("expected_position_before", before),
                            ("expected_position_after", after),
                        )
                    )
                    categorical_match = detected_state == case["expected_state"] and position_match
            elif kind == "driver_story":
                rows = connection.execute(
                    """select story_status, story_direction
                    from marts.race_control_impact
                    where season=? and round=? and event_number=? and driver_code=?""",
                    [case["season"], case["round"], event_number, case["driver"]],
                ).fetchall()
                covered = bool(rows)
                if rows:
                    detected_state, direction = map(str, rows[0])
                    categorical_match = detected_state == case["expected_state"] and (
                        case.get("expected_direction") is None
                        or direction == case["expected_direction"]
                    )
            else:
                rows = connection.execute(
                    """select pit_timing_class from marts.race_control_impact
                    where season=? and round=? and event_number=? and driver_code=?""",
                    [case["season"], case["round"], event_number, case["driver"]],
                ).fetchall()
                covered = bool(rows)
                detected_state = str(rows[0][0]) if rows else None
                if rows and case["expected_state"] in {
                    "interval_crosses_zero",
                    "insufficient_references",
                }:
                    effects = connection.execute(
                        """select eligible, lower_bound, upper_bound, exclusion_reason
                        from marts.race_control_effects
                        where season=? and round=? and event_number=? and driver_code=?
                        and effect_type in ('estimated_vsc_pit_saving',
                            'estimated_safety_car_pit_saving')""",
                        [case["season"], case["round"], event_number, case["driver"]],
                    ).fetchall()
                    if any(
                        eligible
                        and lower is not None
                        and upper is not None
                        and float(lower) <= 0 <= float(upper)
                        for eligible, lower, upper, _ in effects
                    ):
                        detected_state = "interval_crosses_zero"
                    elif any(
                        not eligible and str(reason).startswith("Fewer than")
                        for eligible, _, _, reason in effects
                    ):
                        detected_state = "insufficient_references"
                categorical_match = detected_state == case["expected_state"]
            coverage_expectation = case.get("coverage_expectation", "covered")
            if coverage_expectation == "source_limited":
                outcome = "expected_unavailable" if not covered else "unexpected_coverage"
            else:
                outcome = (
                    "uncovered" if not covered else "matched" if categorical_match else "mismatch"
                )
            results.append(
                {
                    "id": case["id"],
                    "kind": kind,
                    "annotation_group": case.get("annotation_group"),
                    "covered": covered,
                    "detected_state": detected_state,
                    "expected_state": case["expected_state"],
                    "outcome": outcome,
                }
            )
            continue
        else:
            raise ValueError(f"Unknown annotation kind: {kind}")
        assert coverage is not None
        covered = coverage[0] == high - low + 1
        laps = sorted(int(row[0]) for row in detections if row[0] is not None)
        exact = any(low <= lap <= high for lap in laps)
        # Negative windows must not be expanded into unrelated positive events.
        margin = int(case.get("lap_tolerance", tolerance)) if expected else 0
        matched = any(low - margin <= lap <= high + margin for lap in laps)
        coverage_expectation = case.get("coverage_expectation", "covered")
        if schema_version == 2 and coverage_expectation == "source_limited":
            outcome = "expected_unavailable" if not covered else "unexpected_coverage"
        else:
            outcome = (
                "uncovered"
                if not covered
                else "true_positive"
                if matched and expected
                else "false_positive"
                if matched
                else "false_negative"
                if expected
                else "true_negative"
            )
        results.append(
            {
                "id": case["id"],
                "kind": kind,
                "annotation_group": case.get("annotation_group"),
                "covered": covered,
                "exact_match": exact,
                "tolerant_match": matched,
                "detected_pair_laps": laps,
                "outcome": outcome,
            }
        )
    counts = {
        name: sum(r["outcome"] == name for r in results)
        for name in [
            "true_positive",
            "true_negative",
            "false_positive",
            "false_negative",
            "uncovered",
            "matched",
            "mismatch",
            "expected_unavailable",
            "unexpected_coverage",
        ]
    }
    positives = counts["true_positive"] + counts["false_negative"]
    predicted_positives = counts["true_positive"] + counts["false_positive"]
    groups = sorted({str(r.get("annotation_group") or r["kind"]) for r in results})
    report = {
        "counts": counts,
        "exact_positive_matches": sum(
            r["covered"]
            and r.get("exact_match", False)
            and (
                bool(c.get("expected", False))
                if schema_version == 1
                else c.get("expected_state") in {"present", "detected"}
            )
            for r, c in zip(results, cases, strict=True)
        ),
        "coverage_basis": "At least one source row per annotated driver-lap; control probes also require a race-control source partition. Not continuous feed completeness.",
        "annotated_cases": len(cases),
        "covered_cases": sum(result["covered"] for result in results),
        "annotated_positive_recall": counts["true_positive"] / positives if positives else None,
        "annotated_precision": (
            counts["true_positive"] / predicted_positives if predicted_positives else None
        ),
        "population_precision": None,
        "population_false_positive_rate": None,
        "limitations": "Purposive, non-exhaustive, single-reviewer annotations. Unmentioned events are unknown, not false positives. No population accuracy or calibrated interval.",
        "cases": results,
    }
    if schema_version == 2:
        report["confusion_matrices"] = {
            group: {
                outcome: sum(
                    result["outcome"] == outcome
                    and str(result.get("annotation_group") or result["kind"]) == group
                    for result in results
                )
                for outcome in counts
            }
            for group in groups
        }
        report["validation_pass"] = not any(
            counts[name]
            for name in (
                "false_positive",
                "false_negative",
                "uncovered",
                "mismatch",
                "unexpected_coverage",
            )
        )
        report["limitations"] = (
            "Stratified, purposive official-source annotations; precision and recall apply "
            "only to this annotated set. No population accuracy or calibrated interval."
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=Path("data/dashboard/latest.duckdb"))
    parser.add_argument(
        "--reference", type=Path, default=Path("validation/reference-events-v1.json")
    )
    parser.add_argument("--output", type=Path, help="Also write the JSON report to this path.")
    args = parser.parse_args()
    # Git may check out CRLF on Windows; hash the UTF-8, LF-normalized reference.
    content = args.reference.read_text(encoding="utf-8").encode("utf-8")
    with duckdb.connect(str(args.snapshot), read_only=True) as connection:
        result = evaluate(connection, json.loads(content))
        result["snapshot_metadata"] = connection.execute(
            "select version, generated_at from dashboard.snapshot_metadata"
        ).fetchall()
    result["reference_sha256"] = hashlib.sha256(content).hexdigest()
    rendered = json.dumps(result, indent=2, default=str, allow_nan=False)
    if args.output is not None:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if result.get("validation_pass") is False:
        raise SystemExit("FAIL: reference validation contains a covered mismatch")


if __name__ == "__main__":
    main()
