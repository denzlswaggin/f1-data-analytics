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
        "driver season history",
        "select count(*) from marts.mart_driver_season_pace where driver_id = 'max_verstappen'",
    ),
    Check(
        "Saturday vs Sunday profile",
        "select count(*) from marts.driver_pace_profile where n_race_comparisons >= 10",
    ),
    Check(
        "2024 Bahrain race laps",
        "select count(*) from marts.mart_lap_times "
        "where season = 2024 and race_name = 'Bahrain Grand Prix'",
        500,
    ),
    Check(
        "2024 Bahrain pit strategy",
        "select count(*) from marts.mart_pit_strategy "
        "where season = 2024 and race_name = 'Bahrain Grand Prix'",
        20,
    ),
    Check(
        "2024 Bahrain tyre strategy",
        "select count(*) from marts.mart_stint_strategy "
        "where season = 2024 and race_name = 'Bahrain Grand Prix'",
        20,
    ),
    Check(
        "2024 Bahrain speed trap",
        "select count(*) from marts.mart_speed_trap "
        "where season = 2024 and race_name = 'Bahrain Grand Prix'",
        15,
    ),
    Check(
        "weather degradation",
        "select count(*) from marts.mart_weather_degradation",
    ),
    Check(
        "weather-covered races",
        "select count(distinct cast(season as varchar) || '-' || cast(round as varchar)) "
        "from marts.mart_weather_degradation where weather_bucket is not null",
    ),
    Check(
        "2024 Bahrain telemetry drivers",
        "select count(distinct driver_code) from marts.mart_lap_telemetry "
        "where season = 2024 and round = 1",
        15,
    ),
    Check(
        "2024 Bahrain replay rows",
        "select count(*) from marts.race_replay where season = 2024 and round = 1",
        10_000,
    ),
    Check(
        "2024 Bahrain replay drivers",
        "select count(distinct driver_code) from marts.race_replay "
        "where season = 2024 and round = 1",
        15,
    ),
    Check(
        "2024 Bahrain replay duration",
        "select coalesce(max(t_s) - min(t_s), 0) from marts.race_replay "
        "where season = 2024 and round = 1",
        3_000,
    ),
    Check(
        "2024 Bahrain overtakes",
        "select count(*) from marts.race_overtakes where season = 2024 and round = 1",
    ),
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
