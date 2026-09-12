"""Reproducibility and freshness audit for a published dashboard snapshot."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import duckdb

from ingestion.dashboard_snapshot import validate_dashboard_snapshot

AuditStatus = Literal["pass", "warn", "fail"]


@dataclass(frozen=True)
class AuditFinding:
    check: str
    status: AuditStatus
    detail: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_state(repository: Path) -> dict[str, Any]:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return {"sha": None, "dirty": None}
    return {"sha": sha, "dirty": dirty}


def _manifest_path(snapshot: Path) -> Path:
    if snapshot.name == "latest.duckdb":
        return snapshot.with_name("latest.json")
    return snapshot.with_suffix(".json")


def audit_dashboard_data(
    snapshot: Path,
    *,
    manifest_path: Path | None = None,
    lake_dir: Path | None = None,
    repository: Path | None = None,
    today: dt.date | None = None,
    verify_checksum: bool = True,
) -> dict[str, Any]:
    """Return a machine-readable audit without mutating the snapshot or warehouse."""
    snapshot = snapshot.resolve()
    repository = (repository or Path.cwd()).resolve()
    today = today or dt.datetime.now(dt.UTC).date()
    findings: list[AuditFinding] = []

    if not snapshot.is_file():
        return {
            "snapshot": str(snapshot),
            "status": "fail",
            "findings": [
                asdict(AuditFinding("snapshot_exists", "fail", "snapshot file is missing"))
            ],
        }

    try:
        latest_event = validate_dashboard_snapshot(snapshot)
    except (OSError, ValueError) as exc:
        findings.append(AuditFinding("snapshot_contract", "fail", str(exc)))
        latest_event = None
    else:
        findings.append(AuditFinding("snapshot_contract", "pass", "serving contract is valid"))

    manifest_file = (manifest_path or _manifest_path(snapshot)).resolve()
    manifest: dict[str, Any] | None = None
    if manifest_file.is_file():
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            findings.append(AuditFinding("manifest", "fail", f"cannot read manifest: {exc}"))
        else:
            findings.append(AuditFinding("manifest", "pass", str(manifest_file)))
    else:
        findings.append(AuditFinding("manifest", "warn", f"missing {manifest_file}"))

    if manifest is not None:
        expected_size = manifest.get("size_bytes")
        actual_size = snapshot.stat().st_size
        if expected_size == actual_size:
            findings.append(AuditFinding("manifest_size", "pass", f"{actual_size} bytes"))
        else:
            findings.append(
                AuditFinding(
                    "manifest_size",
                    "fail",
                    f"manifest={expected_size}, snapshot={actual_size}",
                )
            )
        expected_hash = manifest.get("sha256")
        if verify_checksum and expected_hash:
            actual_hash = _sha256(snapshot)
            status: AuditStatus = "pass" if actual_hash == expected_hash else "fail"
            findings.append(AuditFinding("manifest_sha256", status, actual_hash))
        provenance_keys = ("schema_version", "git_sha", "package_versions", "methodology_versions")
        missing_provenance = [key for key in provenance_keys if key not in manifest]
        if "git_sha" in manifest and not manifest["git_sha"]:
            missing_provenance.append("git_sha")
        if missing_provenance:
            findings.append(
                AuditFinding(
                    "provenance",
                    "warn",
                    "legacy manifest is missing " + ", ".join(missing_provenance),
                )
            )
        else:
            findings.append(AuditFinding("provenance", "pass", "manifest provenance is complete"))

    table_rows: dict[str, int] = {}
    methodology_versions: dict[str, list[str]] = {}
    latest_completed: str | None = None
    with duckdb.connect(str(snapshot), read_only=True) as connection:
        for schema, table in connection.execute(
            "select table_schema, table_name from information_schema.tables "
            "where table_schema in ('staging', 'intermediate', 'marts') "
            "order by table_schema, table_name"
        ).fetchall():
            qualified = f'"{schema}"."{table}"'
            count_row = connection.execute(f"select count(*) from {qualified}").fetchone()
            if count_row is None:
                raise ValueError(f"could not count {schema}.{table}")
            table_rows[f"{schema}.{table}"] = int(count_row[0])
        row = connection.execute(
            "select max(race_date) from staging.stg_races where race_date < ?",
            [today],
        ).fetchone()
        latest_completed = None if row is None or row[0] is None else str(row[0])
        for schema, table in connection.execute(
            "select table_schema, table_name from information_schema.columns "
            "where column_name = 'methodology_version' "
            "and table_schema in ('staging', 'intermediate', 'marts') "
            "order by table_schema, table_name"
        ).fetchall():
            qualified = f'"{schema}"."{table}"'
            values = connection.execute(
                f"select distinct methodology_version from {qualified} "
                "where methodology_version is not null order by methodology_version"
            ).fetchall()
            methodology_versions[f"{schema}.{table}"] = [str(value[0]) for value in values]

    if latest_completed and latest_event and latest_completed > latest_event:
        findings.append(
            AuditFinding(
                "freshness",
                "fail",
                f"data ends {latest_event}; calendar has completed event {latest_completed}",
            )
        )
    else:
        findings.append(
            AuditFinding(
                "freshness",
                "pass",
                f"data={latest_event or 'unknown'}, calendar={latest_completed or 'unknown'}",
            )
        )

    lake_files = 0
    lake_bytes = 0
    if lake_dir is not None and lake_dir.is_dir():
        for path in lake_dir.rglob("*.parquet"):
            lake_files += 1
            lake_bytes += path.stat().st_size

    git = _git_state(repository)
    if git["dirty"]:
        findings.append(AuditFinding("repository", "warn", "working tree has uncommitted changes"))
    elif git["sha"]:
        findings.append(AuditFinding("repository", "pass", str(git["sha"])))

    overall: AuditStatus = "pass"
    if any(finding.status == "fail" for finding in findings):
        overall = "fail"
    elif any(finding.status == "warn" for finding in findings):
        overall = "warn"
    return {
        "snapshot": str(snapshot),
        "manifest": str(manifest_file),
        "audited_at": dt.datetime.now(dt.UTC).isoformat(),
        "status": overall,
        "latest_event_date": latest_event,
        "latest_completed_event_date": latest_completed,
        "table_rows": table_rows,
        "methodology_versions": methodology_versions,
        "git": git,
        "lake": {
            "directory": str(lake_dir) if lake_dir else None,
            "files": lake_files,
            "bytes": lake_bytes,
        },
        "findings": [asdict(finding) for finding in findings],
    }
