"""Read-only exact-lap agreement with complete official listed-stop windows.

The source defines listed stops, not every possible pit visit. This is source
agreement on selected windows, not global truth, an independent sensor, held-out
race validation, or timing/uncertainty calibration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import duckdb


def validate_reference(reference: dict[str, Any]) -> list[dict[str, Any]]:
    """Reject ambiguous denominators before querying any model output."""
    if not isinstance(reference, dict) or type(reference.get("schema_version")) is not int:
        raise ValueError("schema_version must be integer 1")
    if reference["schema_version"] != 1 or not isinstance(reference.get("windows"), list):
        raise ValueError("Unsupported reference schema")
    windows = reference["windows"]
    ids: set[str] = set()
    previous: list[dict[str, Any]] = []
    for window in windows:
        if not isinstance(window, dict):
            raise ValueError("Each window must be an object")
        identifier = window.get("id")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in ids:
            raise ValueError("Window IDs must be unique nonempty strings")
        ids.add(identifier)
        if window.get("kind") != "pit_entry" or window.get("complete") is not True:
            raise ValueError("Only complete pit_entry windows are supported")
        for key in ("season", "round", "lap_min", "lap_max"):
            if type(window.get(key)) is not int or window[key] < 1:
                raise ValueError(f"{key} must be a positive integer")
        if window["lap_min"] > window["lap_max"]:
            raise ValueError("Inverted lap bounds")
        driver = window.get("driver")
        if not isinstance(driver, str) or not driver.strip():
            raise ValueError("driver must be a nonempty string")
        source = window.get("source_url")
        if not isinstance(source, str):
            raise ValueError("source_url must be an HTTP(S) URL")
        parsed = urlparse(source)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("source_url must be an HTTP(S) URL")
        expected = window.get("expected_laps")
        if not isinstance(expected, list) or any(
            type(lap) is not int or not window["lap_min"] <= lap <= window["lap_max"]
            for lap in expected
        ):
            raise ValueError("expected_laps must contain integer laps inside the window")
        if len(set(expected)) != len(expected):
            raise ValueError("Duplicate expected laps")
        for other in previous:
            if all(
                window[key] == other[key] for key in ("season", "round", "driver", "kind")
            ) and max(window["lap_min"], other["lap_min"]) <= min(
                window["lap_max"], other["lap_max"]
            ):
                raise ValueError("Overlapping windows would double-count events")
        previous.append(window)
    return windows


def evaluate(connection: duckdb.DuckDBPyConnection, reference: dict[str, Any]) -> dict[str, Any]:
    windows = validate_reference(reference)
    results = []
    totals = {"true_positive": 0, "false_negative": 0, "false_positive": 0}
    for window in windows:
        rows = connection.execute(
            """select lap_number, is_pit_in_lap from marts.pit_lap_context
            where season=? and round=? and driver_code=? and lap_number between ? and ?
            order by lap_number""",
            [window[key] for key in ("season", "round", "driver", "lap_min", "lap_max")],
        ).fetchall()
        observed = {row[0] for row in rows}
        missing = sorted(set(range(window["lap_min"], window["lap_max"] + 1)) - observed)
        unknown = sorted({row[0] for row in rows if row[1] is None})
        candidates = [row[0] for row in rows if row[1] is True]
        expected = sorted(window["expected_laps"])
        covered = not missing and not unknown
        matched = sorted(set(candidates) & set(expected))
        counts: dict[str, int | None] = {
            "true_positive": len(matched) if covered else None,
            "false_negative": len(expected) - len(matched) if covered else None,
            "false_positive": len(candidates) - len(matched) if covered else None,
        }
        if covered:
            for key, value in counts.items():
                assert value is not None
                totals[key] += value
        results.append(
            {
                **window,
                "covered": covered,
                "scored": covered,
                "unscored_reason": (
                    "missing_source_laps" if missing else "unknown_pit_flags" if unknown else None
                ),
                "required_lap_count": window["lap_max"] - window["lap_min"] + 1,
                "available_lap_count": len(observed),
                "missing_laps": missing,
                "unknown_flag_laps": unknown,
                "candidate_laps": candidates,
                "duplicate_candidate_laps": sorted(
                    lap for lap, count in Counter(candidates).items() if count > 1
                ),
                "matched_laps": matched if covered else None,
                "missed_expected_laps": sorted(set(expected) - set(candidates))
                if covered
                else None,
                **counts,
                "precision": len(matched) / len(candidates) if covered and candidates else None,
                "recall": len(matched) / len(expected) if covered and expected else None,
            }
        )
    predicted = totals["true_positive"] + totals["false_positive"]
    actual = totals["true_positive"] + totals["false_negative"]
    return {
        "annotated_windows": len(windows),
        "scored_windows": sum(result["scored"] for result in results),
        "unscored_windows": [result["id"] for result in results if not result["scored"]],
        "counts": totals,
        "scored_candidate_events": predicted,
        "scored_expected_events": actual,
        "precision": totals["true_positive"] / predicted if predicted else None,
        "recall": totals["true_positive"] / actual if actual else None,
        "coverage_basis": "Every annotated driver-lap must have a context row and no unknown pit flag; not continuous telemetry completeness.",
        "matching": "Exact lap, one-to-one; duplicate detections count as extra false positives.",
        "limitations": "Selected complete official listed-stop windows only. False positives are source disagreements, not proof of no pit visit. Not global truth, an independent sensor, held-out race validation, or timing/uncertainty calibration. No true negatives or population false-positive rate.",
        "windows": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=Path("data/dashboard/latest.duckdb"))
    parser.add_argument("--reference", type=Path, default=Path("validation/pit-windows-v1.json"))
    args = parser.parse_args()
    # read_text normalizes Windows CRLF to LF before hashing the frozen reference.
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
