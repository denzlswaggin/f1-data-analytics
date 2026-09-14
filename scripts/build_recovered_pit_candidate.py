"""Build an isolated dashboard candidate from a verified pit recovery capture."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import duckdb
import pandas as pd
from analytics.pipeline import (
    build_all_pace_consistency,
    build_all_pit_timing_sensitivity,
    build_all_pit_window_effectiveness,
    build_all_racecraft_battles,
    build_all_traffic_adjusted_pace,
    build_all_tyre_warmup,
)
from analytics.pit_recovery import recover_pit_timestamps
from ingestion.config import Settings


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def build(snapshot: Path, capture: Path, stops_warehouse: Path, output: Path) -> None:
    manifest = json.loads((capture / "manifest.json").read_text(encoding="utf-8"))
    if not manifest["complete"] or digest(snapshot) != manifest["baseline_sha256"]:
        raise ValueError("Complete capture and exact baseline snapshot required")
    with duckdb.connect(str(snapshot), read_only=True) as connection:
        baseline = connection.sql("select * from staging.stg_laps where session = 'R'").df()
    expected = set(baseline[["season", "round"]].itertuples(index=False, name=None))
    scopes = [(r["season"], r["round"]) for r in manifest["races"]]
    if len(set(scopes)) != len(scopes) or set(scopes) != expected:
        raise ValueError("Capture race scope does not match the baseline")
    recovered = []
    for race in manifest["races"]:
        name = f"{race['season']}-{race['round']:02}-source.parquet"
        if race["status"] != "reconciled" or race["source_file"] != name:
            raise ValueError("Rejected race or unexpected source filename")
        source = capture / name
        if digest(source) != race["source_sha256"]:
            raise ValueError("Captured source hash mismatch")
        old = baseline.loc[baseline.season.eq(race["season"]) & baseline["round"].eq(race["round"])]
        recovered.append(recover_pit_timestamps(old, pd.read_parquet(source)))
    # Read views in their original catalog before opening the new candidate.
    with duckdb.connect(str(stops_warehouse), read_only=True) as connection:
        stops = connection.sql("select * from staging.stg_pitstops").df()
    output.mkdir(parents=True, exist_ok=False)
    target = output / "f1.duckdb"
    shutil.copyfile(snapshot, target)
    if digest(target) != manifest["baseline_sha256"]:
        raise ValueError("Baseline changed while copying")
    laps = pd.concat(recovered, ignore_index=True)
    with duckdb.connect(str(target)) as connection:
        connection.register("recovered_laps", laps)
        connection.register("recorded_stops", stops)
        connection.execute(
            "create or replace table staging.stg_pitstops as select * from recorded_stops"
        )
        connection.execute("""
            update staging.stg_laps as a
            set pit_in_time_sec = b.pit_in_time_sec, pit_out_time_sec = b.pit_out_time_sec
            from recovered_laps as b
            where a.season = b.season and a.round = b.round and a.session = b.session
                and a.driver_code = b.driver_code and a.lap_number = b.lap_number
        """)
    settings = Settings(duckdb_path=target)
    for builder in (
        build_all_racecraft_battles,
        build_all_traffic_adjusted_pace,
        build_all_pace_consistency,
        build_all_tyre_warmup,
        build_all_pit_window_effectiveness,
        build_all_pit_timing_sensitivity,
    ):
        print(f"Rebuilding {builder.__name__}", flush=True)
        builder(settings=settings)
    print(f"Candidate built: {target}; validate before publication", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--stops-warehouse", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new directory")
    args = parser.parse_args()
    build(args.snapshot, args.capture, args.stops_warehouse, args.output)


if __name__ == "__main__":
    main()
