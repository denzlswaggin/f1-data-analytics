"""Build immutable DuckDB snapshots for the static Evidence dashboard.

The operational warehouse remains the system of record.  A dashboard build
consumes a compact, read-only snapshot instead of running a historical backfill
inside the Pages workflow.  Snapshots can be produced from either development
DuckDB or production Postgres and optionally published to object storage.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
from sqlalchemy import create_engine, inspect, text

from ingestion.config import Settings, get_settings

DASHBOARD_SCHEMAS = ("staging", "intermediate", "marts")
REQUIRED_TABLES = (
    ("staging", "stg_races"),
    ("marts", "driver_ratings"),
    ("marts", "driver_ratings_v2"),
    ("marts", "mart_driver_season_pace"),
)


@dataclass(frozen=True)
class SnapshotManifest:
    """Metadata shipped next to one immutable dashboard database."""

    version: str
    generated_at: str
    source: str
    database_file: str
    sha256: str
    size_bytes: int
    latest_event_date: str | None
    table_rows: dict[str, int]


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _scalar(connection: duckdb.DuckDBPyConnection, query: str) -> Any:
    row = connection.execute(query).fetchone()
    if row is None:
        raise ValueError(f"snapshot query returned no row: {query}")
    return row[0]


def _version(now: dt.datetime) -> str:
    revision = os.getenv("GITHUB_SHA", "local")[:8]
    return f"{now:%Y%m%dT%H%M%SZ}-{revision}"


def _copy_duckdb(source: Path, target: Path) -> dict[str, int]:
    if not source.is_file():
        raise FileNotFoundError(f"DuckDB warehouse does not exist: {source}")
    source_sql = str(source.resolve()).replace("'", "''")
    connection = duckdb.connect(str(target))
    rows: dict[str, int] = {}
    try:
        # dbt views in the development warehouse are bound to its normal `f1`
        # catalog name. Attach under that name, then materialize every relation so
        # the snapshot remains valid regardless of its eventual filename.
        connection.execute(f"ATTACH '{source_sql}' AS f1 (READ_ONLY)")
        tables = connection.execute(
            "select table_schema, table_name from information_schema.tables "
            "where table_catalog = 'f1' and table_schema in (?, ?, ?) "
            "order by table_schema, table_name",
            list(DASHBOARD_SCHEMAS),
        ).fetchall()
        for schema, table in tables:
            connection.execute(f"create schema if not exists {_quote(schema)}")
            qualified = f"{_quote(schema)}.{_quote(table)}"
            connection.execute(f"create table {qualified} as select * from f1.{qualified}")
            rows[f"{schema}.{table}"] = int(
                _scalar(connection, f"select count(*) from {qualified}")
            )
        connection.execute("detach f1")
    finally:
        connection.close()
    return rows


def _copy_postgres(settings: Settings, target: Path) -> dict[str, int]:
    engine = create_engine(settings.pg_dsn)
    target_connection = duckdb.connect(str(target))
    rows: dict[str, int] = {}
    try:
        inspector = inspect(engine)
        with engine.connect() as source_connection:
            for schema in DASHBOARD_SCHEMAS:
                target_connection.execute(f"create schema if not exists {_quote(schema)}")
                names = sorted(
                    set(inspector.get_table_names(schema=schema))
                    | set(inspector.get_view_names(schema=schema))
                )
                for table_name in names:
                    qualified = f"{_quote(schema)}.{_quote(table_name)}"
                    count = 0
                    first = True
                    query = text(f"select * from {qualified}")
                    for frame in pd.read_sql_query(query, source_connection, chunksize=50_000):
                        target_connection.register("snapshot_chunk", frame)
                        if first:
                            target_connection.execute(
                                f"create table {qualified} as select * from snapshot_chunk"
                            )
                            first = False
                        elif not frame.empty:
                            target_connection.execute(
                                f"insert into {qualified} by name select * from snapshot_chunk"
                            )
                        count += len(frame)
                        target_connection.unregister("snapshot_chunk")
                    rows[f"{schema}.{table_name}"] = count
    finally:
        target_connection.close()
        engine.dispose()
    return rows


def _validate_snapshot(path: Path) -> str | None:
    connection = duckdb.connect(str(path), read_only=True)
    try:
        available = {
            (str(schema), str(table))
            for schema, table in connection.execute(
                "select table_schema, table_name from information_schema.tables"
            ).fetchall()
        }
        missing = sorted(set(REQUIRED_TABLES) - available)
        if missing:
            raise ValueError(f"dashboard snapshot is missing required tables: {missing}")
        if _scalar(connection, "select count(*) from marts.driver_ratings") == 0:
            raise ValueError("dashboard snapshot contains no driver ratings")
        value = _scalar(connection, "select max(race_date) from staging.stg_races")
        return None if value is None else str(value)
    finally:
        connection.close()


def _write_snapshot_metadata(
    path: Path,
    *,
    version: str,
    generated_at: dt.datetime,
    source: str,
    latest_event_date: str | None,
) -> None:
    connection = duckdb.connect(str(path))
    try:
        connection.execute("create schema if not exists dashboard")
        connection.execute(
            "create table dashboard.snapshot_metadata as "
            "select ?::varchar as version, ?::timestamptz as generated_at, "
            "?::varchar as source, ?::date as latest_event_date",
            [version, generated_at, source, latest_event_date],
        )
    finally:
        connection.close()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.")
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json(payload: dict[str, Any], target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, target)


def _publish(path: Path, manifest_path: Path, publish_uri: str, version: str) -> None:
    import fsspec

    base = publish_uri.rstrip("/")
    filesystem, root = fsspec.core.url_to_fs(base)
    version_root = f"{root.rstrip('/')}/{version}"
    filesystem.makedirs(version_root, exist_ok=True)
    filesystem.put(str(path), f"{version_root}/{path.name}")
    filesystem.put(str(manifest_path), f"{version_root}/{manifest_path.name}")
    filesystem.put(str(manifest_path), f"{root.rstrip('/')}/latest.json")


def build_dashboard_snapshot(
    output_dir: Path,
    *,
    settings: Settings | None = None,
    version: str | None = None,
    publish_uri: str | None = None,
    now: dt.datetime | None = None,
) -> SnapshotManifest:
    """Build, validate and atomically publish one versioned dashboard snapshot."""
    settings = settings or get_settings()
    now = now or dt.datetime.now(dt.UTC)
    version = version or _version(now)
    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / f"f1-dashboard-{version}.duckdb"
    if final_path.exists():
        raise FileExistsError(f"snapshot version already exists: {version}")

    descriptor, temporary_name = tempfile.mkstemp(
        dir=output_dir, prefix=f".{version}.", suffix=".duckdb"
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    temporary.unlink()
    try:
        table_rows = (
            _copy_duckdb(settings.duckdb_path, temporary)
            if settings.warehouse == "duckdb"
            else _copy_postgres(settings, temporary)
        )
        latest_event_date = _validate_snapshot(temporary)
        _write_snapshot_metadata(
            temporary,
            version=version,
            generated_at=now,
            source=settings.warehouse,
            latest_event_date=latest_event_date,
        )
        os.replace(temporary, final_path)
    finally:
        temporary.unlink(missing_ok=True)

    manifest = SnapshotManifest(
        version=version,
        generated_at=now.isoformat(),
        source=settings.warehouse,
        database_file=final_path.name,
        sha256=_sha256(final_path),
        size_bytes=final_path.stat().st_size,
        latest_event_date=latest_event_date,
        table_rows=table_rows,
    )
    manifest_path = output_dir / f"f1-dashboard-{version}.json"
    _write_json(asdict(manifest), manifest_path)
    _atomic_copy(final_path, output_dir / "latest.duckdb")
    _write_json(asdict(manifest), output_dir / "latest.json")
    if publish_uri:
        _publish(final_path, manifest_path, publish_uri, version)
    return manifest


def fetch_dashboard_snapshot(uri: str, output: Path) -> SnapshotManifest:
    """Resolve ``latest.json``, verify its immutable database and install it locally."""
    import fsspec

    base = uri.rstrip("/")
    filesystem, root = fsspec.core.url_to_fs(base)
    with filesystem.open(f"{root.rstrip('/')}/latest.json", "rb") as handle:
        payload = json.load(handle)
    manifest = SnapshotManifest(**payload)
    remote = f"{root.rstrip('/')}/{manifest.version}/{manifest.database_file}"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    try:
        filesystem.get(remote, str(temporary))
        if _sha256(temporary) != manifest.sha256:
            raise ValueError("downloaded dashboard snapshot checksum does not match its manifest")
        _validate_snapshot(temporary)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    _write_json(asdict(manifest), output.with_suffix(".json"))
    return manifest
