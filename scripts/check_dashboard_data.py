"""Fail a dashboard deployment when its default views have no usable data."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import duckdb


@dataclass(frozen=True)
class Check:
    name: str
    query: str
    minimum: int | float = 1


def latest_race_check(
    name: str, table: str, expression: str = "count(*)", minimum: int | float = 1
) -> Check:
    """Build a cross-dialect check for the newest available partition of a mart."""
    query = (
        f"with latest as (select season, round from {table} group by season, round "
        f"order by season desc, round desc limit 1) select {expression} from {table} "
        "join latest using (season, round)"
    )
    return Check(name, query, minimum)


CHECKS = (
    Check(
        "driver ratings",
        "select count(*) from marts.driver_ratings where n_comparisons >= 40",
        15,
    ),
    Check(
        "driver rating intervals",
        "select count(*) from marts.driver_ratings "
        "where n_comparisons >= 40 and rating_lo is not null and rating_hi is not null "
        "and rating_lo <= rating_hi",
        15,
    ),
    Check(
        "latest dynamic rating intervals",
        "select count(*) from marts.driver_ratings_v2 "
        "where season = (select max(season) from marts.driver_ratings_v2) "
        "and rating_lo is not null and rating_hi is not null "
        "and rating_lo <= rating and rating <= rating_hi",
        15,
    ),
    Check(
        "driver season history",
        "select count(*) from marts.mart_driver_season_pace where driver_id = 'max_verstappen'",
    ),
    Check(
        "Saturday vs Sunday profile",
        "select count(*) from marts.driver_pace_profile where n_race_comparisons >= 10",
    ),
    latest_race_check("latest race laps", "marts.mart_lap_times", minimum=100),
    latest_race_check("latest race pit strategy", "marts.mart_pit_strategy", minimum=10),
    latest_race_check("latest race tyre strategy", "marts.mart_stint_strategy", minimum=10),
    latest_race_check("latest race speed trap", "marts.mart_speed_trap", minimum=15),
    Check(
        "weather degradation",
        "select count(*) from marts.mart_weather_degradation",
    ),
    Check(
        "weather-covered races",
        "select count(distinct cast(season as varchar) || '-' || cast(round as varchar)) "
        "from marts.mart_weather_degradation where weather_bucket is not null",
    ),
    latest_race_check(
        "latest telemetry drivers",
        "marts.mart_lap_telemetry",
        "count(distinct driver_code)",
        10,
    ),
    latest_race_check("latest replay rows", "marts.race_replay", minimum=10_000),
    latest_race_check(
        "latest replay drivers",
        "marts.race_replay",
        "count(distinct driver_code)",
        10,
    ),
    latest_race_check(
        "latest replay duration",
        "marts.race_replay",
        "coalesce(max(t_s) - min(t_s), 0)",
        1_800,
    ),
    latest_race_check("latest race overtakes", "marts.race_overtakes"),
)


def main() -> None:
    warehouse = Path(os.getenv("F1_DUCKDB_PATH", "data/warehouse/f1.duckdb"))
    failures: list[str] = []

    with duckdb.connect(str(warehouse), read_only=True) as connection:
        for check in CHECKS:
            try:
                value = connection.execute(check.query).fetchone()[0]
            except duckdb.Error as exc:
                failures.append(f"{check.name}: query failed ({exc})")
                continue

            if value is None or value < check.minimum:
                failures.append(f"{check.name}: got {value}, expected at least {check.minimum}")
            else:
                print(f"PASS {check.name}: {value}")

    if failures:
        details = "\n".join(f"FAIL {failure}" for failure in failures)
        raise SystemExit(f"Dashboard data checks failed:\n{details}")


if __name__ == "__main__":
    main()
