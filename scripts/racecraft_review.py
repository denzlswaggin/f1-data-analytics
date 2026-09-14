"""Prepare blind pair-window annotations and score only independently reviewed windows.

Reviewer attestations are auditable declarations, not authentication or proof
that footage was watched. Never populate them from detector outputs.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
from scripts.report_pass_windows import evaluate as evaluate_windows

DEFINITION = {
    "id": "sustained-pair-pass-v1",
    "minimum_hold_seconds": 3,
    "lap_tolerance": 0,
    "scope": "Directed on-track position exchanges between the named pair, held continuously for at least three seconds. Include position returns; exclude pit-cycle changes, lapping and retirements. Annotate all events in both directions on the anchor driver's lap convention. This does not establish competitive intent or ten-second Racecraft pressure.",
}
SCOPE_FIELDS = ("id", "season", "round", "pair", "anchor_driver", "lap_min", "lap_max")


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def make_packet(reference: dict[str, Any]) -> dict[str, Any]:
    """Remove previous expected events and narrative hints from reviewer packets."""
    windows = [{key: window[key] for key in SCOPE_FIELDS} for window in reference["windows"]]
    protocol = {
        "schema_version": 1,
        "definition": copy.deepcopy(DEFINITION),
        "selection": "Previously inspected diagnostic pair windows; not untouched races or a population sample.",
        "windows": windows,
    }
    # Reuse the structural validator without manufacturing source observations.
    with duckdb.connect() as connection:
        connection.execute("create schema marts")
        connection.execute(
            "create table marts.race_replay(season int, round int, driver_code varchar, t_s double, lap_number int)"
        )
        connection.execute(
            "create table marts.race_overtakes(season int, round int, t_s double, passer_code varchar, passed_code varchar)"
        )
        evaluate_windows(connection, as_reference(protocol))
    return {"protocol": protocol, "protocol_sha256": digest(protocol)}


def as_reference(protocol: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "lap_tolerance": protocol["definition"]["lap_tolerance"],
        "windows": [
            {
                **window,
                "expected": [],
                "completeness": "provisional",
                "source_url": "https://www.formula1.com/",
            }
            for window in protocol["windows"]
        ],
    }


def empty_review(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocol_sha256": packet["protocol_sha256"],
        "reviewer_id": None,
        "independent_of_detector": False,
        "windows": [
            {
                "id": window["id"],
                "complete": False,
                "footage_url": None,
                "footage_start_s": None,
                "footage_end_s": None,
                "reviewed_at": None,
                "events": [],
                "uncertainties": ["Not reviewed"],
            }
            for window in packet["protocol"]["windows"]
        ],
    }


def _reviewed_events(review: dict[str, Any], window: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only events with explicit direction, lap and measured hold evidence."""
    if review.get("complete") is not True or review.get("uncertainties") != []:
        raise ValueError("incomplete_or_uncertain_review")
    if not isinstance(review.get("footage_url"), str) or not review["footage_url"].startswith(
        "https://"
    ):
        raise ValueError("missing_footage")
    start: Any = review.get("footage_start_s")
    end: Any = review.get("footage_end_s")
    if (
        any(type(value) not in (int, float) or not math.isfinite(value) for value in (start, end))
        or not 0 <= start < end
    ):
        raise ValueError("invalid_footage_bounds")
    if not isinstance(review.get("reviewed_at"), str) or not review["reviewed_at"].strip():
        raise ValueError("missing_review_date")
    datetime.fromisoformat(review["reviewed_at"])
    events = review.get("events")
    if not isinstance(events, list):
        raise ValueError("invalid_events")
    previous = start - 1
    previous_hold = start
    result: list[dict[str, Any]] = []
    for event in events:
        lap, when, held = (
            event.get("lap_number"),
            event.get("footage_t_s"),
            event.get("held_until_s"),
        )
        if type(lap) is not int or not window["lap_min"] <= lap <= window["lap_max"]:
            raise ValueError("invalid_event_lap")
        if {event.get("passer_code"), event.get("passed_code")} != set(window["pair"]):
            raise ValueError("invalid_event_direction")
        if (
            any(
                type(value) not in (int, float) or not math.isfinite(value)
                for value in (when, held)
            )
            or not start <= when < held <= end
            or when <= previous
            or when < previous_hold
        ):
            raise ValueError("invalid_event_timing")
        if held - when < DEFINITION["minimum_hold_seconds"]:
            raise ValueError("insufficient_hold_evidence")
        previous = when
        previous_hold = held
        if result and result[-1]["passer_code"] == event["passer_code"]:
            raise ValueError("nonalternating_pair_sequence")
        result.append({key: event[key] for key in ("lap_number", "passer_code", "passed_code")})
    return result


def score(
    connection: duckdb.DuckDBPyConnection, packet: dict[str, Any], reviews: list[dict[str, Any]]
) -> dict[str, Any]:
    protocol = packet["protocol"]
    if (
        packet.get("protocol_sha256") != digest(protocol)
        or protocol.get("definition") != DEFINITION
        or protocol.get("schema_version") != 1
    ):
        raise ValueError("Changed or unsupported frozen protocol")
    identities = [review.get("reviewer_id") for review in reviews]
    ready = len(reviews) == 2 and all(
        isinstance(identity, str) and identity.strip() for identity in identities
    )
    if ready and len({str(identity).strip().casefold() for identity in identities}) != 2:
        raise ValueError("Two distinct reviewers required")
    for review in reviews:
        if review.get("protocol_sha256") != packet["protocol_sha256"]:
            raise ValueError("Review belongs to another protocol")
        ids = [window["id"] for window in review["windows"]]
        if len(ids) != len(set(ids)) or set(ids) != {
            window["id"] for window in protocol["windows"]
        }:
            raise ValueError("Review window coverage mismatch")
    reference = as_reference(protocol)
    reasons = {}
    for window in reference["windows"]:
        try:
            if not ready or not all(
                review.get("independent_of_detector") is True for review in reviews
            ):
                raise ValueError("two_independent_reviews_required")
            annotations = [
                _reviewed_events(
                    next(row for row in review["windows"] if row["id"] == window["id"]), window
                )
                for review in reviews
            ]
            if annotations[0] != annotations[1]:
                raise ValueError("reviewer_disagreement")
            window["expected"] = annotations[0]
        except ValueError as exc:
            reasons[window["id"]] = str(exc)
    diagnostics = evaluate_windows(connection, reference)
    order_available = "running_order" in {
        row[0] for row in connection.execute("describe marts.race_replay").fetchall()
    }
    totals = {"true_positive": 0, "false_positive": 0, "false_negative": 0}
    results = []
    for window in diagnostics["windows"]:
        reason = reasons.get(window["id"])
        if not window["covered"]:
            reason = reason or "incomplete_replay_coverage"
        if not order_available:
            reason = reason or "missing_order_evidence"
        elif window["covered"]:
            scope = next(row for row in reference["windows"] if row["id"] == window["id"])
            invalid = connection.execute(
                "select count(*) from marts.race_replay where season=? and round=? "
                "and driver_code in (?,?) and t_s between ? and ? "
                "and (running_order is null or not isfinite(running_order) or running_order < 1)",
                [
                    scope["season"],
                    scope["round"],
                    *scope["pair"],
                    window["start_t_s"],
                    window["end_t_s"],
                ],
            ).fetchone()
            if invalid and invalid[0]:
                reason = reason or "missing_order_evidence"
        counts = None
        if reason is None:
            matching = window["matching"]
            counts = {
                "true_positive": len(matching["matches"]),
                "false_positive": len(matching["unmatched_observed_indices"]),
                "false_negative": len(matching["unmatched_expected_indices"]),
            }
            for key, value in counts.items():
                totals[key] += value
        results.append(
            {
                "id": window["id"],
                "scored": reason is None,
                "reason": reason,
                "counts": counts,
                "coverage": window["coverage"],
            }
        )
    scored = sum(window["scored"] for window in results)
    tp, fp, fn = totals.values()
    return {
        "protocol_sha256": packet["protocol_sha256"],
        "review_sha256": [digest(review) for review in reviews],
        "scored_windows": scored,
        "total_windows": len(results),
        "counts": totals if scored else None,
        "selected_window_precision": tp / (tp + fp) if tp + fp else None,
        "selected_window_recall": tp / (tp + fn) if tp + fn else None,
        "population_accuracy": None,
        "limitations": "Self-declared reviewer identity, independence and exhaustive footage coverage are not authenticated. Counts apply only to covered agreed windows and exact anchor-lap sequence matching. Unscored windows are not negatives. No population accuracy, false-positive rate, calibrated confidence or competitive-skill claim.",
        "windows": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--reference", type=Path, default=Path("validation/pass-windows-v1.json"))
    prepare.add_argument("--output", type=Path, required=True)
    scoring = sub.add_parser("score")
    scoring.add_argument("--packet", type=Path, required=True)
    scoring.add_argument("--review", type=Path, action="append", required=True)
    scoring.add_argument("--snapshot", type=Path, default=Path("data/dashboard/latest.duckdb"))
    args = parser.parse_args()
    if args.command == "prepare":
        packet = make_packet(json.loads(args.reference.read_text(encoding="utf-8")))
        args.output.mkdir(parents=True, exist_ok=False)
        for name, value in [
            ("packet.json", packet),
            ("reviewer-a.json", empty_review(packet)),
            ("reviewer-b.json", empty_review(packet)),
        ]:
            (args.output / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    else:
        packet = json.loads(args.packet.read_text(encoding="utf-8"))
        reviews = [json.loads(path.read_text(encoding="utf-8")) for path in args.review]
        with duckdb.connect(str(args.snapshot), read_only=True) as connection:
            result = score(connection, packet, reviews)
            result["snapshot_metadata"] = connection.execute(
                "select version, generated_at from dashboard.snapshot_metadata"
            ).fetchall()
        with args.snapshot.open("rb") as snapshot_file:
            result["snapshot_sha256"] = hashlib.file_digest(snapshot_file, "sha256").hexdigest()
        print(json.dumps(result, indent=2, default=str, allow_nan=False))


if __name__ == "__main__":
    main()
