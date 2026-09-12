from __future__ import annotations

import datetime as dt
from pathlib import Path

from ingestion.config import Settings
from ingestion.dashboard_snapshot import build_dashboard_snapshot
from ingestion.data_audit import audit_dashboard_data

from tests.test_dashboard_snapshot import _warehouse


def test_data_audit_verifies_snapshot_and_provenance(tmp_path: Path) -> None:
    source = tmp_path / "source.duckdb"
    _warehouse(source)
    settings = Settings(warehouse="duckdb", duckdb_path=source, lake_dir=tmp_path / "lake")
    output = tmp_path / "snapshots"
    build_dashboard_snapshot(
        output,
        settings=settings,
        version="audit-v1",
        now=dt.datetime(2026, 8, 30, tzinfo=dt.UTC),
    )

    report = audit_dashboard_data(
        output / "latest.duckdb",
        repository=Path.cwd(),
        today=dt.date(2026, 8, 31),
    )

    assert report["status"] in {"pass", "warn"}
    statuses = {finding["check"]: finding["status"] for finding in report["findings"]}
    assert statuses["snapshot_contract"] == "pass"
    assert statuses["manifest_sha256"] == "pass"
    assert statuses["provenance"] == "pass"
    assert statuses["freshness"] == "pass"


def test_data_audit_detects_missing_snapshot(tmp_path: Path) -> None:
    snapshot = tmp_path / "missing.duckdb"
    report = audit_dashboard_data(snapshot)
    assert report["status"] == "fail"
