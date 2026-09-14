"""Trace pair order to lap interpolation; this is not an independent event label."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
from analytics.replay import _progress_curve


def diagnose(connection: duckdb.DuckDBPyConnection, window: dict[str, Any]) -> dict[str, Any]:
    pair = window["pair"]
    replay = connection.execute(
        "select driver_code,t_s,lap_number,running_order from marts.race_replay "
        "where season=? and round=? and driver_code in (?,?) order by t_s,driver_code",
        [window["season"], window["round"], *pair],
    ).fetchdf()
    anchor = replay.loc[
        replay.driver_code.eq(window["anchor_driver"])
        & replay.lap_number.between(window["lap_min"], window["lap_max"])
    ]
    if anchor.empty:
        raise ValueError("No anchor replay in the requested window")
    start, end = float(anchor.t_s.min()), float(anchor.t_s.max())
    laps = connection.execute(
        "select driver_code,lap_number,lap_start_sec,lap_time_sec from staging.stg_laps "
        "where season=? and round=? and session='R' order by driver_code,lap_number",
        [window["season"], window["round"]],
    ).fetchdf()
    origin = float(laps.lap_start_sec.min())
    # Difference of two piecewise-linear progress curves has extrema at the
    # union of their knots. Inspect those as well as recorded replay samples.
    pair_laps = laps.loc[laps.driver_code.isin(pair)].dropna(subset=["lap_start_sec"])
    ends = pair_laps.lap_start_sec + pair_laps.lap_time_sec.fillna(0)
    knots = np.unique(
        np.concatenate(
            (
                [origin + start, origin + end],
                ends.loc[ends.between(origin + start, origin + end)].to_numpy(),
            )
        )
    )
    curves = [
        _progress_curve(knots, pair_laps.loc[pair_laps.driver_code.eq(driver)]) for driver in pair
    ]
    difference = curves[0] - curves[1]
    if not np.isfinite(difference).all():
        raise ValueError("Missing finite lap interpolation support")
    orders = {}
    for driver in pair:
        frame = replay.loc[replay.driver_code.eq(driver) & replay.t_s.between(start, end)]
        orders[driver] = {
            "samples": len(frame),
            "running_orders": sorted(int(value) for value in frame.running_order.dropna().unique()),
        }
    return {
        "window_id": window["id"],
        "pair": pair,
        "start_t_s": start,
        "end_t_s": end,
        "race_origin_session_s": origin,
        "replay_order": orders,
        "interpolation_knots_session_s": knots.tolist(),
        "first_minus_second_progress_laps": difference.tolist(),
        "first_always_ahead_in_interpolation": bool((difference > 0).all()),
        "second_always_ahead_in_interpolation": bool((difference < 0).all()),
        "lap_inputs": json.loads(
            pair_laps.loc[
                pair_laps.lap_number.between(window["lap_min"] - 1, window["lap_max"] + 1)
            ].to_json(orient="records")
        ),
        "limitations": "Reproduces the current lap-interpolation model, not physical on-track order. A constant modeled lead cannot exclude a real within-lap exchange. Does not determine whether the three-second pass definition was met. X/Y affects activity and pass proximity but is not the running-order ranking variable.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=Path("data/dashboard/latest.duckdb"))
    parser.add_argument("--reference", type=Path, default=Path("validation/pass-windows-v1.json"))
    parser.add_argument("--window", default="austria-2025-mclaren-lap11")
    args = parser.parse_args()
    reference = json.loads(args.reference.read_text(encoding="utf-8"))
    window = next(row for row in reference["windows"] if row["id"] == args.window)
    with duckdb.connect(str(args.snapshot), read_only=True) as connection:
        result = diagnose(connection, window)
        result["snapshot_metadata"] = connection.execute(
            "select version, generated_at from dashboard.snapshot_metadata"
        ).fetchall()
    with args.snapshot.open("rb") as snapshot_file:
        result["snapshot_sha256"] = hashlib.file_digest(snapshot_file, "sha256").hexdigest()
    print(json.dumps(result, indent=2, default=str, allow_nan=False))


if __name__ == "__main__":
    main()
