from pathlib import Path

import duckdb
import pytest
from ingestion.snapshot_coverage import validate_partition_preservation


def test_lost_partition_requires_an_explicit_reason(tmp_path: Path) -> None:
    old, new = tmp_path / "old.duckdb", tmp_path / "new.duckdb"
    for path, rounds in [(old, "(2026,13),(2026,14)"), (new, "(2026,14)")]:
        with duckdb.connect(str(path)) as c:
            c.execute("create schema marts")
            c.execute(
                f"create table marts.weather as select * from (values {rounds}) t(season,round)"
            )
    with pytest.raises(ValueError, match="lose published"):
        validate_partition_preservation(old, new)
    validate_partition_preservation(
        old,
        new,
        [{"table": "marts.weather", "season": 2026, "round": 13, "reason": "source correction"}],
    )


def test_legacy_partition_can_leave_snapshot_during_scope_migration(tmp_path: Path) -> None:
    old, new = tmp_path / "old.duckdb", tmp_path / "new.duckdb"
    for path, rounds in [(old, "(2023,1),(2024,1)"), (new, "(2024,1)")]:
        with duckdb.connect(str(path)) as connection:
            connection.execute("create schema marts")
            connection.execute(
                f"create table marts.weather as select * from (values {rounds}) t(season,round)"
            )
    validate_partition_preservation(old, new)


def test_coverage_gate_requires_attempt_receipt_and_correct_count() -> None:
    from ingestion.snapshot_coverage import (
        SOURCE_TABLES,
        materialize_source_coverage,
        validate_source_coverage,
    )

    with duckdb.connect() as c:
        c.execute("create schema staging")
        c.execute("create schema marts")
        c.execute("create table staging.stg_results as select 2026 season, 14 round")
        for table in SOURCE_TABLES.values():
            c.execute(f"create table {table} (season integer, round integer)")
        materialize_source_coverage(c)
        with pytest.raises(ValueError, match="Source coverage invalid"):
            validate_source_coverage(c)
        c.execute(
            "update marts.source_coverage set status='no_observations', reason='Successful empty source response'"
        )
        validate_source_coverage(c)
        c.execute("insert into staging.stg_weather values (2026,14)")
        with pytest.raises(ValueError, match="weather"):
            validate_source_coverage(c)
        materialize_source_coverage(c)
        validate_source_coverage(c)


def test_lost_session_is_a_regression_even_if_race_remains(tmp_path: Path) -> None:
    old, new = tmp_path / "old.duckdb", tmp_path / "new.duckdb"
    for path, sessions in [(old, "('R'),('Q'),(null)"), (new, "('R')")]:
        with duckdb.connect(str(path)) as c:
            c.execute("create schema staging")
            c.execute(
                f"create table staging.laps as select 2026 season, 14 round, session from (values {sessions}) t(session)"
            )
    with pytest.raises(ValueError, match="lose published"):
        validate_partition_preservation(old, new)
