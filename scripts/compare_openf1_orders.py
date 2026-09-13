"""Compare captured position-change observations with reconstructed replay order.

No source disagreements are converted to false positives, misses or accuracy
estimates: the feeds may share an origin and have different event definitions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any

import duckdb

MAX_CLOCK_SPREAD_S = 1.0


def utc_seconds(value: str) -> float:
    timestamp = datetime.fromisoformat(value)
    if timestamp.tzinfo is None:
        raise ValueError("Source timestamps must include a timezone")
    return timestamp.timestamp()


def load_capture(directory: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest["schema_version"] not in (1, 2):
        raise ValueError("Unsupported capture schema")
    drivers = manifest["drivers"]
    if len(drivers) != 2 or len(set(drivers)) != 2:
        raise ValueError("Capture requires two distinct drivers")
    expected = {
        "sessions.json",
        "overtakes.json",
        *(f"{endpoint}-{driver}.json" for endpoint in ("laps", "position") for driver in drivers),
    }
    if manifest["schema_version"] == 2:
        expected.update(f"intervals-{driver}.json" for driver in drivers)
    files = manifest["files"]
    if {item["file"] for item in files} != expected or len(files) != len(expected):
        raise ValueError("Incomplete or duplicate source capture")
    data = {}
    for item in files:
        expected_parameters = {"session_key": manifest["session_key"]}
        stem = item["file"].removesuffix(".json")
        endpoint = stem.split("-")[0]
        if "-" in stem:
            expected_parameters["driver_number"] = int(stem.split("-")[1])
        if item["endpoint"] != endpoint or item["parameters"] != expected_parameters:
            raise ValueError("Capture query does not match response filename")
        raw = (directory / item["file"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != item["sha256"] or item["http_status"] != 200:
            raise ValueError("Source response failed integrity validation")
        rows = json.loads(raw)
        if (
            not isinstance(rows, list)
            or len(rows) != item["rows"]
            or any(row.get("session_key") != manifest["session_key"] for row in rows)
        ):
            raise ValueError("Source rows do not match capture scope")
        if "driver_number" in item["parameters"] and any(
            row.get("driver_number") != item["parameters"]["driver_number"] for row in rows
        ):
            raise ValueError("Source driver does not match capture scope")
        data[item["file"]] = rows
    return manifest, data


def position_timeline(
    rows: dict[int, list[dict[str, Any]]], start: float, end: float
) -> dict[str, Any]:
    """Apply simultaneous updates together; never infer a swap across unknown order."""
    if len(rows) != 2 or not math.isfinite(start) or not math.isfinite(end) or start >= end:
        raise ValueError("A finite window and two driver streams are required")
    updates: dict[float, dict[int, int | None]] = defaultdict(dict)
    for driver, observations in rows.items():
        for row in observations:
            if row["driver_number"] != driver:
                raise ValueError("Wrong driver in position stream")
            when = utc_seconds(row["date"])
            rank = row.get("position")
            rank = rank if type(rank) is int and rank > 0 else None
            if driver in updates[when] and updates[when][driver] != rank:
                raise ValueError("Conflicting simultaneous driver positions")
            updates[when][driver] = rank
    state: dict[int, int | None] = dict.fromkeys(rows)
    latest_update: dict[int, float] = {}

    def leader() -> int | None:
        first, second = state
        a, b = state[first], state[second]
        if a is None or b is None or a == b:
            return None
        return first if a < b else second

    ordered = sorted(updates.items())
    for when, batch in ordered:
        if when >= start:
            break
        state.update(batch)
        latest_update.update(dict.fromkeys(batch, when))
    segments: list[tuple[float, int | None]] = [(start, leader())]
    for when, batch in ordered:
        if not start <= when < end:
            continue
        state.update(batch)
        current = leader()
        if current != segments[-1][1]:
            segments.append((when, current))
    transitions = []
    uncertain = []
    for index, (when, current) in enumerate(segments):
        until = segments[index + 1][0] if index + 1 < len(segments) else end
        if current is None:
            if until > when:
                uncertain.append({"start_utc_s": when, "end_utc_s": until})
        elif index and segments[index - 1][1] is not None:
            transitions.append(
                {
                    "utc_s": when,
                    "overtaking_driver_number": current,
                    "overtaken_driver_number": segments[index - 1][1],
                    "inferred_state_duration_s": round(until - when, 6),
                    "right_censored": index + 1 == len(segments),
                }
            )
    return {
        "baseline_available": segments[0][1] is not None,
        "baseline_last_updates_utc_s": latest_update,
        "ambiguous_or_missing_intervals": uncertain,
        "transitions": transitions,
        "complete_source_coverage": None,
        "limitations": "Sparse change events are carried forward between updates. State duration is not a measured physical lead duration. Continuous source delivery cannot be inferred from this stream.",
    }


def clock_alignment(anchors: list[dict[str, Any]]) -> dict[str, Any]:
    if len(anchors) != 4:
        raise ValueError("Four bracketing driver/lap anchors are required")
    offsets = [utc_seconds(row["source_timestamp"]) - row["replay_t_s"] for row in anchors]
    if not all(math.isfinite(value) for value in offsets):
        raise ValueError("Nonfinite clock alignment")
    spread = max(offsets) - min(offsets)
    if spread > MAX_CLOCK_SPREAD_S:
        raise ValueError("Clock anchors disagree by more than one second")
    return {
        "utc_minus_replay_s": median(offsets),
        "spread_s": spread,
        "maximum_spread_s": MAX_CLOCK_SPREAD_S,
        "anchors": anchors,
    }


def compare(
    connection: duckdb.DuckDBPyConnection,
    manifest: dict[str, Any],
    data: dict[str, Any],
    window: dict[str, Any],
) -> dict[str, Any]:
    sessions = data["sessions.json"]
    if (
        len(sessions) != 1
        or sessions[0]["session_name"] != "Race"
        or sessions[0]["year"] != window["season"]
    ):
        raise ValueError("Captured session is not the requested race season")
    dates = connection.execute(
        "select race_date from staging.stg_races where season=? and round=?",
        [window["season"], window["round"]],
    ).fetchall()
    if len(dates) != 1 or str(dates[0][0]) != sessions[0]["date_start"][:10]:
        raise ValueError("Captured session date does not match snapshot race")
    laps = connection.execute(
        "select driver_code,driver_number,lap_number,lap_start_sec,lap_time_sec from staging.stg_laps where season=? and round=? and session='R'",
        [window["season"], window["round"]],
    ).fetchdf()
    origin = float(laps.lap_start_sec.min())
    driver_map = {}
    anchors = []
    for code in window["pair"]:
        numbers = laps.loc[laps.driver_code.eq(code), "driver_number"].dropna().unique()
        if len(numbers) != 1 or int(numbers[0]) not in manifest["drivers"]:
            raise ValueError("Missing or ambiguous source driver mapping")
        number = int(numbers[0])
        driver_map[number] = code
        for lap in (window["lap_min"], window["lap_max"] + 1):
            boundary = "lap_start"
            local = laps.loc[laps.driver_code.eq(code) & laps.lap_number.eq(lap)]
            source = [
                row
                for row in data[f"laps-{number}.json"]
                if row["lap_number"] == lap and row.get("date_start")
            ]
            if lap == window["lap_max"] + 1 and local.empty and not source:
                # Only a recorded final-lap finish can replace a next-lap start.
                # Missing interior laps must still fail closed.
                local_last = laps.loc[laps.driver_code.eq(code), "lap_number"].max()
                source_last = max(
                    (row["lap_number"] for row in data[f"laps-{number}.json"]), default=0
                )
                if local_last == window["lap_max"] and source_last == window["lap_max"]:
                    lap -= 1
                    boundary = "recorded_lap_end"
                    local = laps.loc[laps.driver_code.eq(code) & laps.lap_number.eq(lap)]
                    source = [
                        row
                        for row in data[f"laps-{number}.json"]
                        if row["lap_number"] == lap and row.get("date_start")
                    ]
            if len(local) != 1 or len(source) != 1:
                raise ValueError("Missing or duplicate bracketing lap anchor")
            source_time = source[0]["date_start"]
            local_time = float(local.iloc[0].lap_start_sec) - origin
            if boundary == "recorded_lap_end":
                durations = [local.iloc[0].lap_time_sec, source[0].get("lap_duration")]
                if any(
                    value is None or not math.isfinite(value) or value <= 0 for value in durations
                ):
                    raise ValueError("Final-lap anchor needs both recorded durations")
                local_time += float(durations[0])
                source_time = (
                    datetime.fromisoformat(source_time) + timedelta(seconds=float(durations[1]))
                ).isoformat()
            anchors.append(
                {
                    "driver_code": code,
                    "driver_number": number,
                    "lap_number": lap,
                    "boundary": boundary,
                    "source_timestamp": source_time,
                    "replay_t_s": local_time,
                }
            )
    alignment = clock_alignment(anchors)
    bounds = [row["replay_t_s"] for row in anchors if row["driver_code"] == window["anchor_driver"]]
    start, end = bounds
    offset = alignment["utc_minus_replay_s"]
    timeline = position_timeline(
        {number: data[f"position-{number}.json"] for number in driver_map},
        start + offset,
        end + offset,
    )
    for transition in timeline["transitions"]:
        mapped = transition["utc_s"] - offset
        transition["replay_t_s"] = mapped
        transition["snapshot_order_near_transition"] = {}
        for code in window["pair"]:
            row = connection.execute(
                "select t_s,running_order from marts.race_replay where season=? and round=? and driver_code=? and abs(t_s-?)<=1 order by abs(t_s-?),t_s limit 1",
                [window["season"], window["round"], code, mapped, mapped],
            ).fetchone()
            transition["snapshot_order_near_transition"][code] = (
                {"t_s": row[0], "running_order": row[1]} if row else None
            )
    reported = [
        row
        for row in data["overtakes.json"]
        if {row["overtaking_driver_number"], row["overtaken_driver_number"]} == set(driver_map)
        and start + offset <= utc_seconds(row["date"]) < end + offset
    ]
    detected = connection.execute(
        "select t_s,passer_code,passed_code from marts.race_overtakes where season=? and round=? and t_s>=? and t_s<? and ((passer_code=? and passed_code=?) or (passer_code=? and passed_code=?)) order by t_s",
        [window["season"], window["round"], start, end, *window["pair"], *reversed(window["pair"])],
    ).fetchall()
    return {
        "window_id": window["id"],
        "driver_mapping": driver_map,
        "replay_start_t_s": start,
        "replay_end_t_s": end,
        "clock_alignment": alignment,
        "source_position_timeline": timeline,
        "source_overtake_endpoint_rows": reported,
        "snapshot_detected_pair_events": [
            {"t_s": t, "passer_code": passer, "passed_code": passed}
            for t, passer, passed in detected
        ],
        "accuracy": None,
        "independent_video_validation": False,
        "limitations": "Feed comparison only. OpenF1 and FastF1 may share original timing, so agreement is not independent adjudication. Source timestamps are not physical pass times; pit cycles and penalties may change order. Counts are not TP/FP/FN. Mapping is rejected if four bracketing lap clocks disagree by >1 second; this tolerance is a diagnostic policy, not calibrated uncertainty.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, default=Path("data/dashboard/latest.duckdb"))
    parser.add_argument("--reference", type=Path, default=Path("validation/pass-windows-v1.json"))
    parser.add_argument("--window", default="austria-2025-mclaren-lap11")
    args = parser.parse_args()
    manifest, data = load_capture(args.capture)
    reference = json.loads(args.reference.read_text(encoding="utf-8"))
    window = next(row for row in reference["windows"] if row["id"] == args.window)
    with duckdb.connect(str(args.snapshot), read_only=True) as connection:
        result = compare(connection, manifest, data, window)
        result["snapshot_metadata"] = connection.execute(
            "select version,generated_at from dashboard.snapshot_metadata"
        ).fetchall()
    with args.snapshot.open("rb") as snapshot_file:
        result["snapshot_sha256"] = hashlib.file_digest(snapshot_file, "sha256").hexdigest()
    result["capture_manifest_sha256"] = hashlib.sha256(
        (args.capture / "manifest.json").read_text(encoding="utf-8").encode()
    ).hexdigest()
    print(json.dumps(result, indent=2, default=str, allow_nan=False))


if __name__ == "__main__":
    main()
