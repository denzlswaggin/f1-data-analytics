from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import duckdb
import pytest
from ingestion.config import Settings
from ingestion.dashboard_snapshot import build_dashboard_snapshot, fetch_dashboard_snapshot


def _warehouse(path: Path) -> None:
    connection = duckdb.connect(str(path))
    try:
        for schema in ("staging", "intermediate", "marts"):
            connection.execute(f"create schema {schema}")
        connection.execute(
            "create table staging.stg_races as select 2026 season, date '2026-08-30' race_date"
        )
        connection.execute("create table intermediate.gaps as select 1 id")
        connection.execute("create table marts.driver_ratings as select 'driver' driver_id")
        connection.execute("create table marts.driver_ratings_v2 as select 'driver' driver_id")
        connection.execute(
            "create table marts.mart_driver_season_pace as select 'driver' driver_id"
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
