"""Portable PostgreSQL backups and destructive-isolated restore drills."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import connection

from ingestion.config import Settings, get_settings


def _postgres_env(settings: Settings) -> dict[str, str]:
    env = os.environ.copy()
    env["PGPASSWORD"] = settings.pg_password
    return env


def _connect(settings: Settings, database: str) -> connection:
    return psycopg2.connect(
        host=settings.pg_host,
        port=settings.pg_port,
        dbname=database,
        user=settings.pg_user,
        password=settings.pg_password,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_postgres_backup(
    directory: Path,
    settings: Settings | None = None,
    *,
    now: dt.datetime | None = None,
) -> Path:
    """Create an atomic custom-format dump and a checksum manifest."""
    settings = settings or get_settings()
    if settings.warehouse != "postgres":
        raise ValueError("PostgreSQL backup requires F1_WAREHOUSE=postgres")
    directory.mkdir(parents=True, exist_ok=True)
    now = now or dt.datetime.now(dt.UTC)
    target = directory / f"f1-{now:%Y%m%dT%H%M%SZ}.dump"
    partial = target.with_suffix(".dump.partial")
    command = [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-acl",
        "--host",
        settings.pg_host,
        "--port",
        str(settings.pg_port),
        "--username",
        settings.pg_user,
        "--dbname",
        settings.pg_database,
        "--file",
        str(partial),
    ]
    try:
        subprocess.run(command, check=True, env=_postgres_env(settings))
        if not partial.is_file() or partial.stat().st_size == 0:
            raise RuntimeError("pg_dump completed without producing a non-empty dump")
        partial.replace(target)
    except Exception:
        partial.unlink(missing_ok=True)
        raise

    manifest = {
        "created_at": now.isoformat(),
        "database": settings.pg_database,
        "file": target.name,
        "bytes": target.stat().st_size,
        "sha256": _sha256(target),
    }
    target.with_suffix(".dump.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return target


def _verify_backup(backup: Path) -> None:
    if not backup.is_file() or backup.stat().st_size == 0:
        raise ValueError(f"backup is missing or empty: {backup}")
    manifest_path = backup.with_suffix(".dump.json")
    if not manifest_path.is_file():
        raise ValueError(f"checksum manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("file") != backup.name or manifest.get("sha256") != _sha256(backup):
        raise ValueError("backup checksum manifest does not match the dump")


def latest_postgres_backup(directory: Path) -> Path:
    """Return the newest timestamp-named dump in a backup directory."""
    backups = sorted(directory.glob("f1-*.dump"))
    if not backups:
        raise ValueError(f"no PostgreSQL dumps found in {directory}")
    return backups[-1]


def run_postgres_restore_drill(backup: Path, settings: Settings | None = None) -> int:
    """Restore into a temporary database, validate the audit table, then remove it.

    The configured user needs CREATEDB for this operation. The production
    database is never selected as a restore target.
    """
    settings = settings or get_settings()
    if settings.warehouse != "postgres":
        raise ValueError("PostgreSQL restore drill requires F1_WAREHOUSE=postgres")
    _verify_backup(backup)
    drill_database = f"f1_restore_drill_{uuid4().hex[:12]}"
    admin = _connect(settings, settings.pg_database)
    admin.autocommit = True
    try:
        with admin.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(drill_database)))
        subprocess.run(
            [
                "pg_restore",
                "--exit-on-error",
                "--no-owner",
                "--no-acl",
                "--host",
                settings.pg_host,
                "--port",
                str(settings.pg_port),
                "--username",
                settings.pg_user,
                "--dbname",
                drill_database,
                str(backup),
            ],
            check=True,
            env=_postgres_env(settings),
        )
        restored = _connect(settings, drill_database)
        try:
            with restored.cursor() as cursor:
                cursor.execute("SELECT to_regclass('raw.ingestion_partitions')")
                table_result = cursor.fetchone()
                if table_result is None or table_result[0] is None:
                    raise RuntimeError("restored database has no raw.ingestion_partitions table")
                cursor.execute("SELECT count(*) FROM raw.ingestion_partitions")
                count_result = cursor.fetchone()
                if count_result is None:
                    raise RuntimeError("restored audit row count returned no result")
                audit_rows = int(count_result[0])
        finally:
            restored.close()
        return audit_rows
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (drill_database,),
            )
            cursor.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(drill_database))
            )
        admin.close()
