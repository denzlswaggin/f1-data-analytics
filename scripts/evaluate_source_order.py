"""Audit experimental pair order and gap availability without publishing marts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import duckdb
from analytics.source_order import MAX_INTERVAL_AGE_S, pair_samples
from scripts.compare_openf1_orders import compare, load_capture


def evaluate(capture: Path, snapshot: Path, window: dict[str, Any]) -> dict[str, Any]:
    manifest, data = load_capture(capture)
    if manifest["schema_version"] != 2:
        raise ValueError("An interval capture is required")
    with duckdb.connect(str(snapshot), read_only=True) as connection:
        comparison = compare(connection, manifest, data, window)
    offset = comparison["clock_alignment"]["utc_minus_replay_s"]
    ticks = list(
        range(math.ceil(comparison["replay_start_t_s"]), math.ceil(comparison["replay_end_t_s"]))
    )
    samples = pair_samples(
        {d: data[f"position-{d}.json"] for d in manifest["drivers"]},
        {d: data[f"intervals-{d}.json"] for d in manifest["drivers"]},
        [t + offset for t in ticks],
    )
    transitions = comparison["source_position_timeline"]["transitions"]
    contexts = []
    for event in transitions:
        surrounding = [
            {**sample, "replay_t_s": round(sample["utc_s"] - offset, 6)}
            for sample in samples
            if -1 <= sample["utc_s"] - event["utc_s"] <= 6
        ]
        contexts.append({"source_event": event, "samples": surrounding})
    with snapshot.open("rb") as stream:
        snapshot_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    return {
        "methodology": "source-pair-audit-v1",
        "window_id": window["id"],
        "snapshot_sha256": snapshot_hash,
        "capture_manifest_sha256": hashlib.sha256(
            (capture / "manifest.json").read_bytes()
        ).hexdigest(),
        "clock_alignment": comparison["clock_alignment"],
        "max_interval_age_s": MAX_INTERVAL_AGE_S,
        "ticks": len(ticks),
        "driver_samples": len(samples),
        "gap_status_counts": dict(Counter(s["gap_status"] for s in samples)),
        "distinct_usable_interval_observations": len(
            {
                (s["driver_number"], s["interval_observed_utc_s"])
                for s in samples
                if s["gap_status"] == "available"
            }
        ),
        "transition_contexts": contexts,
        "snapshot_detected_pair_events": comparison["snapshot_detected_pair_events"],
        "production_promotion": False,
        "accuracy": None,
        "limitations": "Development windows, not holdout accuracy. Pair ranks must not overwrite a full field. Held gaps are not independent pressure observations. Missing position updates cannot be detected without a heartbeat. Same source does not guarantee synchronized order and gaps. No physical-event or independent video verification.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, default=Path("data/dashboard/latest.duckdb"))
    parser.add_argument("--window", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reference = json.loads(Path("validation/pass-windows-v1.json").read_text(encoding="utf-8"))
    window = next(w for w in reference["windows"] if w["id"] == args.window)
    result = evaluate(args.capture, args.snapshot, window)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k not in ("clock_alignment", "transition_contexts")
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
