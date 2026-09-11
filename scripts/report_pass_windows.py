"""Read-only directed pass-sequence diagnostics; provisional labels cannot certify precision."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from itertools import pairwise
from pathlib import Path
from typing import Any

import duckdb
from scripts.pass_sequence_matching import match_sequence


def evaluate(connection: duckdb.DuckDBPyConnection, reference: dict[str, Any]) -> dict[str, Any]:
    if type(reference.get("schema_version")) is not int or reference["schema_version"] != 1:
        raise ValueError("Unsupported schema")
    windows = reference.get("windows")
    tolerance = reference.get("lap_tolerance")
    if not isinstance(windows, list) or type(tolerance) is not int or tolerance < 0:
        raise ValueError("Invalid windows or tolerance")
    seen: list[dict[str, Any]] = []
    for window in windows:
        if not isinstance(window, dict):
            raise ValueError("Invalid window")
        if not isinstance(window.get("id"), str) or not window["id"]:
            raise ValueError("Missing ID")
        pair = window.get("pair")
        if (
            not isinstance(pair, list)
            or len(pair) != 2
            or any(not isinstance(p, str) or not p for p in pair)
            or pair[0] == pair[1]
        ):
            raise ValueError("A window requires two distinct drivers")
        if window.get("anchor_driver") not in pair or window.get("completeness") != "provisional":
            raise ValueError("Only provisional windows with a pair anchor are supported")
        if not isinstance(window.get("source_url"), str) or not window["source_url"].startswith(
            "https://"
        ):
            raise ValueError("Reference source required")
        if any(
            type(window.get(k)) is not int or window[k] < 1
            for k in ("season", "round", "lap_min", "lap_max")
        ):
            raise ValueError("Invalid race or lap identifiers")
        if window["lap_min"] > window["lap_max"] or not isinstance(window.get("expected"), list):
            raise ValueError("Invalid bounds or expected events")
        match_sequence(window["expected"], [], tolerance)
        for event in window["expected"]:
            if {event["passer_code"], event["passed_code"]} != set(pair) or not window[
                "lap_min"
            ] <= event["lap_number"] <= window["lap_max"]:
                raise ValueError("Expected event outside pair or lap scope")
        for old in seen:
            if old["id"] == window["id"]:
                raise ValueError("Duplicate window ID")
            if (
                old["season"] == window["season"]
                and old["round"] == window["round"]
                and set(old["pair"]) == set(pair)
                and max(old["lap_min"], window["lap_min"]) <= min(old["lap_max"], window["lap_max"])
            ):
                raise ValueError("Overlapping pair windows")
        seen.append(window)
    results = []
    for window in windows:
        pair = window["pair"]
        anchor = window["anchor_driver"]
        rows = connection.execute(
            """select driver_code,t_s,lap_number from marts.race_replay
            where season=? and round=? and driver_code in (?,?) order by t_s,driver_code""",
            [window["season"], window["round"], *pair],
        ).fetchall()
        ticks = [
            (float(t), int(lap))
            for driver, t, lap in rows
            if driver == anchor
            and t is not None
            and math.isfinite(t)
            and lap is not None
            and window["lap_min"] <= lap <= window["lap_max"]
        ]
        missing = sorted(
            set(range(window["lap_min"], window["lap_max"] + 1)) - {lap for _, lap in ticks}
        )
        reasons = ["missing_anchor_laps"] if missing else []
        if any(b[1] < a[1] for a, b in pairwise(ticks)):
            reasons.append("nonmonotonic_anchor_laps")
        start = min((t for t, _ in ticks), default=None)
        end = max((t for t, _ in ticks), default=None)
        coverage: dict[str, Any] = {}
        observed = []
        if start is not None and end is not None:
            for driver in pair:
                if any(
                    code == driver
                    and t is not None
                    and math.isfinite(t)
                    and start <= t <= end
                    and lap is None
                    for code, t, lap in rows
                ):
                    reasons.append(f"unknown_lap_ticks:{driver}")
                times = [
                    float(t)
                    for code, t, lap in rows
                    if code == driver
                    and t is not None
                    and math.isfinite(t)
                    and start <= t <= end
                    and lap is not None
                ]
                gaps = [b - a for a, b in pairwise(times)]
                max_gap = max(gaps, default=None)
                covered = (
                    len(times) >= 2
                    and len(set(times)) == len(times)
                    and times[0] <= start + 1
                    and times[-1] >= end - 1
                    and max_gap is not None
                    and max_gap <= 3
                )
                coverage[driver] = {"samples": len(times), "max_gap_s": max_gap, "covered": covered}
                if not covered:
                    reasons.append(f"incomplete_pair_ticks:{driver}")
            events = connection.execute(
                """select t_s,passer_code,passed_code from marts.race_overtakes
                where season=? and round=? and t_s between ? and ?
                and ((passer_code=? and passed_code=?) or (passer_code=? and passed_code=?))
                order by t_s""",
                [window["season"], window["round"], start, end, *pair, *reversed(pair)],
            ).fetchall()
            for t, passer, passed in events:
                nearest = min(ticks, key=lambda tick: (abs(tick[0] - t), tick[0]))
                if abs(nearest[0] - t) > 1:
                    reasons.append("unaligned_pass_timestamp")
                observed.append(
                    {
                        "t_s": float(t),
                        "lap_number": nearest[1],
                        "passer_code": passer,
                        "passed_code": passed,
                    }
                )
        covered = not reasons and start is not None and end is not None
        if len({e["t_s"] for e in observed}) != len(observed):
            reasons.append("ambiguous_simultaneous_pair_events")
            covered = False
        matching = match_sequence(window["expected"], observed, tolerance) if covered else None
        results.append(
            {
                "id": window["id"],
                "pair": pair,
                "anchor_driver": anchor,
                "lap_min": window["lap_min"],
                "lap_max": window["lap_max"],
                "covered": covered,
                "coverage": coverage,
                "missing_anchor_laps": missing,
                "unscored_reasons": reasons,
                "start_t_s": start,
                "end_t_s": end,
                "expected": window["expected"],
                "observed": observed,
                "matching": matching,
                "precision": None,
                "false_positive_count": None,
            }
        )
    return {
        "annotated_windows": len(windows),
        "covered_windows": sum(r["covered"] for r in results),
        "precision": None,
        "population_recall": None,
        "limitations": "Provisional report sequences, not adjudicated exhaustive footage. Unmatched detections require review, not false-positive labels. Anchor-lap assignment and <=3-second pair gaps are operational coverage checks. Short lead exchanges may not satisfy production persistence. No calibrated accuracy or causal skill claims.",
        "windows": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=Path("data/dashboard/latest.duckdb"))
    parser.add_argument("--reference", type=Path, default=Path("validation/pass-windows-v1.json"))
    args = parser.parse_args()
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
