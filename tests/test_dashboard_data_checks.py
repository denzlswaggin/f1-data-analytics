from __future__ import annotations

import duckdb
from scripts.check_dashboard_data import (
    latest_completed_race_coverage_check,
    race_partition_coverage_check,
    recent_season_coverage_check,
)


def test_recent_season_coverage_accepts_all_three_latest_seasons() -> None:
    connection = duckdb.connect()
    connection.execute("create schema staging")
    connection.execute("create schema marts")
    connection.execute(
        "create table staging.stg_results as "
        "select * from (values (2023), (2024), (2025), (2026)) as results(season)"
    )
    connection.execute(
        "create table marts.example as "
        "select * from (values (2024), (2025), (2026)) as seasons(season)"
    )

    check = recent_season_coverage_check("example coverage", "marts.example")

    result = connection.execute(check.query).fetchone()
    assert result is not None
    assert result[0] == 0


def test_recent_season_coverage_reports_a_missing_middle_season() -> None:
    connection = duckdb.connect()
    connection.execute("create schema staging")
    connection.execute("create schema marts")
    connection.execute(
        "create table staging.stg_results as "
        "select * from (values (2024), (2025), (2026)) as results(season)"
    )
    connection.execute(
        "create table marts.example as select * from (values (2024), (2026)) as seasons(season)"
    )

    check = recent_season_coverage_check("example coverage", "marts.example")

    result = connection.execute(check.query).fetchone()
    assert result is not None
    assert result[0] == 1


def test_latest_completed_race_coverage_ignores_future_races() -> None:
    connection = duckdb.connect()
    connection.execute("create schema staging")
    connection.execute("create schema marts")
    connection.execute(
        "create table staging.stg_races as select * from (values "
        "(2025, 1, date '2000-01-01'), (2025, 2, date '2999-01-01')"
        ") as races(season, round, race_date)"
    )
    connection.execute(
        "create table marts.example as select * from (values (2025, 1)) as races(season, round)"
    )

    check = latest_completed_race_coverage_check("latest race", "marts.example")

    assert connection.execute(check.query).fetchone() == (0,)


def test_latest_completed_race_coverage_reports_missing_latest_race() -> None:
    connection = duckdb.connect()
    connection.execute("create schema staging")
    connection.execute("create schema marts")
    connection.execute(
        "create table staging.stg_races as select * from (values "
        "(2025, 1, date '2000-01-01'), (2025, 2, date '2000-01-08')"
        ") as races(season, round, race_date)"
    )
    connection.execute(
        "create table marts.example as select * from (values (2025, 1)) as races(season, round)"
    )

    check = latest_completed_race_coverage_check("latest race", "marts.example")

    assert connection.execute(check.query).fetchone() == (1,)


def test_race_partition_coverage_requires_an_exact_match() -> None:
    connection = duckdb.connect()
    connection.execute("create schema marts")
    connection.execute(
        "create table marts.expected as select * from (values (2025, 1), (2025, 2)) "
        "as races(season, round)"
    )
    connection.execute(
        "create table marts.covered as select * from (values (2025, 1), (2025, 3)) "
        "as races(season, round)"
    )

    check = race_partition_coverage_check("race partitions", "marts.expected", "marts.covered")

    assert connection.execute(check.query).fetchone() == (2,)
