"""Recompute completed races with current inputs and record before/after coverage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from analytics.pipeline import build_pit_timing_sensitivity_incremental
from ingestion.config import Settings, get_settings
from ingestion.loaders.warehouse import read_query


def coverage(settings: Settings, first: int, last: int) -> list[dict[str, object]]:
    return read_query(
        f"""select season, round, race_name, count(*) as observed_stops,
            count(*) filter (where eligible) as eligible_stops,
            count(*) filter (where not eligible) as excluded_stops
        from marts.pit_timing_sensitivity
        where season between {first} and {last}
        group by season, round, race_name order by season, round""",
        settings,
    ).to_dict(orient="records")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-season", type=int, default=2024)
    parser.add_argument("--to-season", type=int, default=2026)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--resume", action="store_true", help="continue the same report and season range"
    )
    args = parser.parse_args()
    if args.from_season > args.to_season:
        parser.error("--from-season must not exceed --to-season")
    if args.report.exists() and not args.resume:
        parser.error("report already exists; use a new path to preserve the baseline")
    if args.resume and not args.report.exists():
        parser.error("--resume requires an existing report")
    settings = get_settings()
    races = read_query(
        f"""select distinct season, round from staging.stg_results
        where season between {args.from_season} and {args.to_season}
        order by season, round""",
        settings,
    )
    report: dict[str, object] = {
        "seasons": [args.from_season, args.to_season],
        "before": coverage(settings, args.from_season, args.to_season),
        "completed": [],
    }
    if args.resume:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        if report.get("seasons") != [args.from_season, args.to_season]:
            parser.error("resume season range must match the original report")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    completed = cast(list[dict[str, int]], report["completed"])
    for season, rnd in races.itertuples(index=False, name=None):
        season, rnd = int(season), int(rnd)
        if {"season": season, "round": rnd} in completed:
            continue
        result = build_pit_timing_sensitivity_incremental(season, rnd, settings=settings)
        completed.append({"season": season, "round": rnd})
        report["completed"] = completed
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(
            f"{season} R{rnd:02}: {len(result.summary)} stops, "
            f"{int(result.summary['eligible'].sum())} eligible",
            flush=True,
        )
    report["after"] = coverage(settings, args.from_season, args.to_season)
    report["exclusions"] = read_query(
        f"""select season, exclusion_reason, count(*) as stops
        from marts.pit_timing_sensitivity
        where season between {args.from_season} and {args.to_season} and not eligible
        group by season, exclusion_reason order by season, stops desc""",
        settings,
    ).to_dict(orient="records")
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
