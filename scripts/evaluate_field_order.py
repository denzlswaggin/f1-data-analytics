"""Evaluate a captured full roster; no production writes or accuracy claims."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import duckdb
from analytics.source_order import MAX_INTERVAL_AGE_S, field_samples
from scripts.compare_openf1_orders import compare, load_capture


def evaluate(directory: Path, snapshot: Path, window: dict[str, Any]) -> dict[str, Any]:
    manifest, data = load_capture(directory)
    if manifest["schema_version"] != 3:
        raise ValueError("A captured full roster is required")
    with duckdb.connect(str(snapshot), read_only=True) as connection:
        numbers = connection.execute(
            "select distinct cast(driver_number as integer) from staging.stg_laps "
            "where season=? and round=? and session='R' and driver_code in (?,?)",
            [window["season"], window["round"], *window["pair"]],
        ).fetchall()
        pair = [row[0] for row in numbers]
        # Project the frozen full capture for the existing four-anchor clock
        # check. This is not another capture or independent corroboration.
        projected = {
            "sessions.json": data["sessions.json"],
            "overtakes.json": data["overtakes.json"],
        }
        for endpoint in ("position", "laps"):
            for driver in pair:
                projected[f"{endpoint}-{driver}.json"] = [
                    r for r in data[f"{endpoint}.json"] if r["driver_number"] == driver
                ]
        comparison = compare(
            connection, {**manifest, "schema_version": 1, "drivers": pair}, projected, window
        )
    offset = comparison["clock_alignment"]["utc_minus_replay_s"]
    ticks = list(
        range(math.ceil(comparison["replay_start_t_s"]), math.ceil(comparison["replay_end_t_s"]))
    )
    samples = field_samples(
        {
            d: [r for r in data["position.json"] if r["driver_number"] == d]
            for d in manifest["drivers"]
        },
        {
            d: [r for r in data["intervals.json"] if r["driver_number"] == d]
            for d in manifest["drivers"]
        },
        [t + offset for t in ticks],
    )
    with snapshot.open("rb") as stream:
        snapshot_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    return {
        "methodology": "source-field-audit-v1",
        "window_id": window["id"],
        "snapshot_sha256": snapshot_hash,
        "capture_manifest_sha256": hashlib.sha256(
            (directory / "manifest.json").read_text(encoding="utf-8").encode()
        ).hexdigest(),
        "roster_size": len(manifest["drivers"]),
        "ticks": len(ticks),
        "driver_samples": len(samples),
        "max_interval_age_s": MAX_INTERVAL_AGE_S,
        "clock_alignment": comparison["clock_alignment"],
        "gap_status_counts": dict(Counter(s["gap_status"] for s in samples)),
        "transition_contexts": [
            {
                "source_event": event,
                "samples": [
                    {**s, "replay_t_s": round(s["utc_s"] - offset, 6)}
                    for s in samples
                    if s["driver_number"] in pair and -1 <= s["utc_s"] - event["utc_s"] <= 6
                ],
            }
            for event in comparison["source_position_timeline"]["transitions"]
        ],
        "production_promotion": False,
        "accuracy": None,
        "limitations": "Declared session roster includes retired/non-starting entries. A coherent 1..N rank state is not proof of a complete timing feed. All earlier gaps are invalidated after any field order change. Held observations never become measured pressure. Clock alignment uses the selected pair's four lap anchors, not every driver's clock. This is a development window, not held-out physical-event validation.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, default=Path("data/dashboard/latest.duckdb"))
    parser.add_argument("--window", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    windows = json.loads(Path("validation/pass-windows-v1.json").read_text(encoding="utf-8"))[
        "windows"
    ]
    result = evaluate(
        args.capture, args.snapshot, next(w for w in windows if w["id"] == args.window)
    )
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result["gap_status_counts"], indent=2))


if __name__ == "__main__":
    main()
