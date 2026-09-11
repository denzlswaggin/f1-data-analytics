"""Fill missing race-control/replay inputs for completed races, preserving other partitions.

Run before exporting a dashboard snapshot. Existing input partitions are reused;
unavailable replay feeds remain excluded by the normal analytics quality checks.
"""

from __future__ import annotations

import argparse
import json

from analytics.pipeline import (
    build_race_control_impact_incremental,
    build_race_replay_incremental,
)
from analytics.replay import IncompleteReplayError
from ingestion.config import get_settings
from ingestion.loaders.warehouse import read_query
from ingestion.pipeline import ingest_positions, ingest_race_control


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-season", type=int, default=2024)
    parser.add_argument("--to-season", type=int, default=2026)
    args = parser.parse_args()
    if args.from_season > args.to_season:
        parser.error("--from-season must not exceed --to-season")
    settings = get_settings()
    races = read_query(
        f"""select distinct season, round from staging.stg_results
        where season between {args.from_season} and {args.to_season}
        order by season, round""",
        settings,
    )
    failures = []
    for season, rnd in races.itertuples(index=False, name=None):
        season, rnd = int(season), int(rnd)
        print(f"Processing {season} round {rnd}", flush=True)
        for table, ingest in (
            ("race_control", ingest_race_control),
            ("positions", ingest_positions),
        ):
            present = read_query(
                f"select count(*) as n from staging.stg_{table} "
                f"where season = {season} and round = {rnd} and session = 'R'",
                settings,
            ).iloc[0, 0]
            if not present:
                ingest(season, [rnd], settings=settings)
        replay_present = read_query(
            f"select count(*) as n from marts.race_replay "
            f"where season = {season} and round = {rnd}",
            settings,
        ).iloc[0, 0]
        if not replay_present:
            try:
                build_race_replay_incremental(season, rnd, settings=settings)
            except IncompleteReplayError as exc:
                failures.append({"season": season, "round": rnd, "reason": str(exc)})
                print(f"Replay excluded: {exc}", flush=True)
        build_race_control_impact_incremental(season, rnd, settings=settings)
    print(json.dumps({"races": len(races), "replay_exclusions": failures}, indent=2))


if __name__ == "__main__":
    main()
