from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import duckdb
import pytest
from ingestion.config import Settings
from ingestion.dashboard_snapshot import (
    DASHBOARD_CONTRACT,
    build_dashboard_snapshot,
    fetch_dashboard_snapshot,
)


def _warehouse(path: Path) -> None:
    connection = duckdb.connect(str(path))
    try:
        for schema in ("staging", "intermediate", "marts"):
            connection.execute(f"create schema {schema}")
        duck_type = {
            "season": "integer",
            "round": "integer",
            "lap_number": "integer",
            "stint": "integer",
            "start_lap": "integer",
            "end_lap": "integer",
            "n_laps": "integer",
            "n_comparisons": "integer",
            "pit_lap": "integer",
            "race_date": "date",
            "rating": "double",
            "rating_lo": "double",
            "rating_hi": "double",
            "form_delta": "double",
            "quali_rating": "double",
            "race_rating": "double",
            "delta": "double",
            "mean_pace_gap": "double",
            "pace_gap": "double",
            "lap_start_sec": "double",
            "session_time_sec": "double",
            "lap_time_sec": "double",
            "duration_sec": "double",
            "top_speed_kph": "double",
            "deg_sec_per_lap": "double",
            "distance_m": "double",
            "speed_kph": "double",
            "t_s": "double",
            "x": "double",
            "y": "double",
        }
        for (schema, table), columns in DASHBOARD_CONTRACT.items():
            definitions = ", ".join(
                f'"{column}" {duck_type.get(column, "varchar")}' for column in sorted(columns)
            )
            connection.execute(f'create table {schema}."{table}" ({definitions})')
        connection.execute(
            "insert into staging.stg_races (season, round, race_name, race_date) "
            "values (2026, 1, 'Test Grand Prix', date '2026-08-30'), "
            "(2026, 2, 'Future Grand Prix', date '2026-12-06')"
        )
        connection.execute(
            "insert into marts.mart_lap_times (season, round) values (2026, 1)"
        )
        connection.execute(
            "insert into marts.driver_ratings "
            "(driver_id, rating, rating_lo, rating_hi, n_comparisons) "
            "values ('driver', 1.0, 0.9, 1.1, 10)"
        )
    finally:
        connection.close()


def test_builds_versioned_snapshot_and_latest_copy(tmp_path: Path) -> None:
    source = tmp_path / "source.duckdb"
    _warehouse(source)
    settings = Settings(warehouse="duckdb", duckdb_path=source, lake_dir=tmp_path / "lake")

    manifest = build_dashboard_snapshot(
        tmp_path / "snapshots",
        settings=settings,
        version="test-v1",
        now=dt.datetime(2026, 8, 30, tzinfo=dt.UTC),
    )

    assert manifest.version == "test-v1"
    assert manifest.latest_event_date == "2026-08-30"
    assert manifest.table_rows["marts.driver_ratings"] == 1
    assert (tmp_path / "snapshots/f1-dashboard-test-v1.duckdb").is_file()
    assert (tmp_path / "snapshots/latest.duckdb").is_file()
    payload = json.loads((tmp_path / "snapshots/latest.json").read_text())
    assert payload["sha256"] == manifest.sha256
    with duckdb.connect(str(tmp_path / "snapshots/latest.duckdb"), read_only=True) as connection:
        metadata = connection.execute(
            "select version, source, latest_event_date from dashboard.snapshot_metadata"
        ).fetchone()
    assert metadata == ("test-v1", "duckdb", dt.date(2026, 8, 30))


def test_fetch_verifies_checksum(tmp_path: Path) -> None:
    source = tmp_path / "source.duckdb"
    _warehouse(source)
    settings = Settings(warehouse="duckdb", duckdb_path=source, lake_dir=tmp_path / "lake")
    published = tmp_path / "published"
    manifest = build_dashboard_snapshot(
        tmp_path / "build",
        settings=settings,
        version="test-v2",
        publish_uri=f"file://{published}",
    )

    installed = tmp_path / "installed/latest.duckdb"
    fetched = fetch_dashboard_snapshot(f"file://{published}", installed)
    assert fetched.sha256 == manifest.sha256
    assert installed.is_file()

    (published / manifest.version / manifest.database_file).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        fetch_dashboard_snapshot(f"file://{published}", installed)


def test_snapshot_rejects_incompatible_dashboard_columns(tmp_path: Path) -> None:
    source = tmp_path / "source.duckdb"
    _warehouse(source)
    with duckdb.connect(str(source)) as connection:
        connection.execute("alter table marts.driver_ratings drop column rating_lo")
    settings = Settings(warehouse="duckdb", duckdb_path=source, lake_dir=tmp_path / "lake")

    with pytest.raises(ValueError, match=r"driver_ratings.*rating_lo"):
        build_dashboard_snapshot(
            tmp_path / "snapshots",
            settings=settings,
            version="broken-columns",
        )
