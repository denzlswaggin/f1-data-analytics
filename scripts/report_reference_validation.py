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
    if reference["schema_version"] != 1 or len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Unsupported schema or duplicate annotation IDs")
    tolerance = reference["lap_tolerance"]
    if type(tolerance) is not int or tolerance < 0:
        raise ValueError("lap_tolerance must be a nonnegative integer")
    results = []
    for case in cases:
        if (
            type(case["expected"]) is not bool
            or case["lap_min"] > case["lap_max"]
            or case["source_id"] not in reference["sources"]
        ):
            raise ValueError("Invalid reference annotation")
        params = [case["season"], case["round"], case["driver"]]
        low, high = case["lap_min"], case["lap_max"]
        kind = case["kind"]
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
        elif kind in {"race_control_start", "race_control_end"}:
            if case["other"] not in {"Safety Car", "VSC", "Red Flag"}:
                raise ValueError("Unknown race-control event type")
            if not case["expected"]:
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
            detections = connection.execute(
                f"select {column} from marts.race_control_events "
                "where season=? and round=? and event_type=?",
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
        else:
            raise ValueError(f"Unknown annotation kind: {kind}")
        assert coverage is not None
        covered = coverage[0] == high - low + 1
        laps = sorted(int(row[0]) for row in detections if row[0] is not None)
        exact = any(low <= lap <= high for lap in laps)
        # Negative windows must not be expanded into unrelated positive events.
        margin = tolerance if case["expected"] else 0
        matched = any(low - margin <= lap <= high + margin for lap in laps)
        outcome = (
            "uncovered"
            if not covered
            else "true_positive"
            if matched and case["expected"]
            else "false_positive"
            if matched
            else "false_negative"
            if case["expected"]
            else "true_negative"
        )
        results.append(
            {
                "id": case["id"],
                "kind": kind,
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
        ]
    }
    positives = counts["true_positive"] + counts["false_negative"]
    return {
        "counts": counts,
        "exact_positive_matches": sum(
            r["covered"] and r["exact_match"] and c["expected"]
            for r, c in zip(results, cases, strict=True)
        ),
        "coverage_basis": "At least one source row per annotated driver-lap; control probes also require a race-control source partition. Not continuous feed completeness.",
        "annotated_cases": len(cases),
        "covered_cases": len(cases) - counts["uncovered"],
        "annotated_positive_recall": counts["true_positive"] / positives if positives else None,
        "population_precision": None,
        "population_false_positive_rate": None,
        "limitations": "Purposive, non-exhaustive, single-reviewer annotations. Unmentioned events are unknown, not false positives. No population accuracy or calibrated interval.",
        "cases": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=Path("data/dashboard/latest.duckdb"))
    parser.add_argument(
        "--reference", type=Path, default=Path("validation/reference-events-v1.json")
    )
    args = parser.parse_args()
    # Git may check out CRLF on Windows; hash the UTF-8, LF-normalized reference.
    content = args.reference.read_text(encoding="utf-8").encode("utf-8")
    with duckdb.connect(str(args.snapshot), read_only=True) as connection:
        result = evaluate(connection, json.loads(content))
        result["snapshot_metadata"] = connection.execute(
            "select version, generated_at from dashboard.snapshot_metadata"
        ).fetchall()
    result["reference_sha256"] = hashlib.sha256(content).hexdigest()
    print(json.dumps(result, indent=2, default=str, allow_nan=False))


if __name__ == "__main__":
    main()
