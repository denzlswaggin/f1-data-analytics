"""Add jointly matched teammate laps from the local FastF1 cache to a candidate.

Existing telemetry points are never replaced. The report records each requested
lap and its outcome. This script does not publish a snapshot; rebuild DNA,
validation and track insights before using the normal snapshot publication gate.
"""

from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path

import duckdb
import pandas as pd
from analytics.driver_dna import _exclusion_reason, select_representative_pair
from ingestion.clients.fastf1_client import resample_lap_telemetry


def expansion_pairs(laps: pd.DataFrame) -> list[tuple[str, int]]:
    """Request one joint eligible pair per team; keep existing eligibility rules."""
    selected: set[tuple[str, int]] = set()
    usable = laps.loc[
        laps.lap_time_sec.gt(0)
        & laps.lap_number.gt(1)
        & laps.pit_in_time_sec.isna()
        & laps.pit_out_time_sec.isna()
        & laps.tyre_life.ge(2)
        & laps.track_status.eq("1")
        & laps.compound.isin(["SOFT", "MEDIUM", "HARD"])
    ].sort_values(["driver_code", "lap_number"])
    for _, team in usable.groupby("team"):
        for a, b in combinations(sorted(team.driver_code.unique()), 2):
            left, right, _ = select_representative_pair(
                team.loc[team.driver_code.eq(a)], team.loc[team.driver_code.eq(b)]
            )
            if _exclusion_reason(left, right) is None:
                selected.update([(str(a), int(left.lap_number)), (str(b), int(right.lap_number))])
    return sorted(selected)


def expand(database: Path, cache: Path, report: Path, season: int | None = None) -> None:
    import fastf1

    if not database.is_file():
        raise FileNotFoundError(database)
    if database.resolve() == Path("data/dashboard/latest.duckdb").resolve():
        raise ValueError("Use a candidate database, never the installed snapshot")
    fastf1.Cache.enable_cache(str(cache))
    fastf1.Cache.offline_mode(True)
    records: list[dict[str, object]] = []
    if report.exists():
        records = json.loads(report.read_text(encoding="utf-8"))["requests"]
    with duckdb.connect(str(database)) as db:
        races = db.execute(
            "select distinct season, round from staging.stg_laps "
            "where session = 'R' and season >= 2024 order by season, round"
        ).fetchall()
        for year, rnd in races:
            if season is not None and year != season:
                continue
            laps = db.execute(
                "select * from staging.stg_laps where season = ? and round = ? and session = 'R'",
                [year, rnd],
            ).df()
            requests = expansion_pairs(laps)
            existing = set(
                db.execute(
                    "select distinct driver_code, lap_number "
                    "from marts.mart_lap_telemetry where season = ? and round = ?",
                    [year, rnd],
                ).fetchall()
            )
            missing = [key for key in requests if key not in existing]
            print(
                f"{year} R{rnd}: {len(requests)} selected laps, {len(missing)} missing", flush=True
            )
            if not missing:
                continue
            try:
                session = fastf1.get_session(year, rnd, "R")
                session.load(laps=True, telemetry=True, weather=False, messages=False)
            except Exception as exc:
                records.append(
                    {
                        "season": year,
                        "round": rnd,
                        "status": "session_unavailable",
                        "reason": str(exc),
                    }
                )
                report.parent.mkdir(parents=True, exist_ok=True)
                report.write_text(json.dumps({"requests": records}, indent=2), encoding="utf-8")
                continue
            for driver, lap_number in missing:
                record: dict[str, object] = {
                    "season": year,
                    "round": rnd,
                    "driver_code": driver,
                    "lap_number": lap_number,
                    "source": "local FastF1 cache",
                }
                try:
                    match = session.laps.loc[
                        session.laps.Driver.eq(driver) & session.laps.LapNumber.eq(lap_number)
                    ]
                    if len(match) != 1:
                        raise ValueError("Expected one cached race lap")
                    points = resample_lap_telemetry(match.iloc[0].get_telemetry(), 25.0)
                    if len(points) < 100:
                        raise ValueError("Fewer than 100 resampled points")
                    points = points.assign(
                        season=year, round=rnd, driver_code=driver, lap_number=lap_number
                    )
                    db.register("new_points", points)
                    db.execute("""insert into marts.mart_lap_telemetry by name
                        select p.*, r.race_name, d.driver_id, d.driver_name, l.compound, l.stint,
                               current_timestamp as source_loaded_at
                        from new_points p
                        join staging.stg_laps l using (season, round, driver_code, lap_number)
                        join staging.stg_races r using (season, round)
                        left join (select distinct season, driver_code, driver_id, driver_name
                                   from staging.stg_driver_codes) d using (season, driver_code)
                        where l.session = 'R'
                    """)
                    db.unregister("new_points")
                    record.update(status="added", points=len(points))
                except Exception as exc:
                    record.update(status="lap_unavailable", reason=str(exc))
                records.append(record)
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps({"requests": records}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=Path("data/fastf1_cache"))
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--season", type=int)
    args = parser.parse_args()
    expand(args.database, args.cache, args.report, args.season)
