from __future__ import annotations

import duckdb
from scripts.check_dashboard_data import recent_season_coverage_check


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
