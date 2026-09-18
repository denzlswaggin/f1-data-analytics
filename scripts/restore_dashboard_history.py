"""Recover missing source partitions without replacing newer published partitions.

Create a separate working database from a serving snapshot. Restore from an
operational warehouse first, optionally query APIs for remaining 2024+ races,
and record provenance and unsuccessful attempts. Run targeted dbt models and
dependent analytics before exporting this candidate; this command never installs it.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path

import duckdb
import pandas as pd
from ingestion.config import Settings
from ingestion.loaders.warehouse import load_dataframe
from ingestion.pipeline import ingest_pitstops, ingest_team_radio, ingest_weather

RESOURCES = {
    "pitstops": """select season, round, driver_id, stop_number as stop,
        pit_lap as lap, cast(null as varchar) as time_of_day,
        cast(duration_sec as varchar) as duration from marts.mart_pit_strategy""",
    "weather": "select * exclude(weather_key) from staging.stg_weather",
    "team_radio": "select * exclude(radio_key) from staging.stg_team_radio",
}


def missing_partitions(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    """Prefer a complete existing partition, never union individual source rows."""
    keys = ["season", "round"] + (["session"] if "session" in incoming else [])
    if existing.empty:
        return incoming.copy()
    present = existing[keys].drop_duplicates().assign(_present=True)
    joined = incoming.merge(present, on=keys, how="left", validate="many_to_one")
    return joined.loc[joined._present.isna(), incoming.columns].copy()


def restore(snapshot: Path, warehouse: Path, output: Path, *, fetch: bool = False) -> None:
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(snapshot, output)
    source_hashes = {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (snapshot, warehouse)
    }
    settings = Settings(warehouse="duckdb", duckdb_path=output)
    records: list[dict[str, object]] = []
    with duckdb.connect(str(output)) as c:
        c.execute("create schema if not exists raw")
        races = c.execute("""select distinct season, round from staging.stg_results
            where season >= 2024 order by season, round""").fetchall()
        for resource, query in RESOURCES.items():
            c.execute(f"create table raw.{resource} as {query}")
    for resource in RESOURCES:
        with duckdb.connect(str(output), read_only=True) as c:
            current = c.execute(f"select * from raw.{resource}").fetchdf()
        with duckdb.connect(str(warehouse), read_only=True) as c:
            historical = c.execute(f"select * from raw.{resource}").fetchdf()
        recovered = missing_partitions(current, historical)
        for season, rows in recovered.groupby("season"):
            load_dataframe(rows, resource, int(season), settings, replace_rounds=True)
        for season, rnd in races:
            published = current[(current.season == season) & (current["round"] == rnd)]
            restored = recovered[(recovered.season == season) & (recovered["round"] == rnd)]
            origin = str(snapshot) if not published.empty else str(warehouse)
            count = len(published) if not published.empty else len(restored)
            status, reason = "available", ""
            if not count:
                origin = "not_attempted"
                status, reason = "not_attempted", "No locally preserved partition"
                if fetch:
                    origin = "source_api"
                    try:
                        fn = {"pitstops": ingest_pitstops, "weather": ingest_weather,
                              "team_radio": ingest_team_radio}[resource]
                        count = fn(int(season), [int(rnd)], settings=settings)
                        status = "available" if count else "no_observations"
                        reason = "" if count else "Ingest returned no observations; not evidence of zero events"
                    except Exception as exc:
                        status, reason = "unavailable", str(exc)[:500]
            records.append(dict(resource=resource, season=season, round=rnd,
                status=status, row_count=count, provenance=origin,
                source_sha256=source_hashes.get(origin), reason=reason))
            print(resource, season, rnd, status, count, flush=True)
    with duckdb.connect(str(output)) as c:
        coverage = pd.DataFrame(records)
        c.register("coverage", coverage)
        c.execute("create or replace table marts.source_coverage as select * from coverage")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=Path("data/dashboard/latest.duckdb"))
    parser.add_argument("--warehouse", type=Path, default=Path("data/warehouse/f1.duckdb"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    restore(args.snapshot, args.warehouse, args.output, fetch=args.fetch)
