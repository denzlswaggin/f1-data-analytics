"""Audit exports preserve provenance, old artifacts and truthful evaluation status."""

import hashlib
import json
from pathlib import Path

import duckdb
import pytest
from scripts.export_audit_evidence import (
    export,
    historical_validation,
    readme_statistics,
    structural_validation,
    update_readme,
    verified_manifest,
)


def test_checksum_failure_keeps_previous_export(tmp_path: Path) -> None:
    snapshot = tmp_path / "latest.duckdb"
    snapshot.write_bytes(b"changed")
    snapshot.with_suffix(".json").write_text(json.dumps({"sha256": "incorrect"}))
    artifact = tmp_path / "evidence.parquet"
    artifact.write_bytes(b"previous")
    with pytest.raises(ValueError, match="checksum"):
        export(snapshot, artifact)
    assert artifact.read_bytes() == b"previous"


def test_manifest_hash_and_database_version_are_both_checked(tmp_path: Path) -> None:
    snapshot = tmp_path / "latest.duckdb"
    with duckdb.connect(str(snapshot)) as c:
        c.execute(
            "create schema dashboard; create table dashboard.snapshot_metadata as select 'actual' as version"
        )
    manifest = {"sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(), "version": "wrong"}
    snapshot.with_suffix(".json").write_text(json.dumps(manifest))
    assert verified_manifest(snapshot) == manifest
    with pytest.raises(ValueError, match="version"):
        export(snapshot, tmp_path / "evidence.parquet")


def test_historical_evaluation_requires_matching_hash(tmp_path: Path) -> None:
    directory = tmp_path / "validation/dashboard-audit-20260918"
    directory.mkdir(parents=True)
    report = {
        "snapshot_sha256": "old",
        "snapshot_metadata": [["old-version", "date"]],
        "model_mae_sec": 1.2,
        "baseline_mae_sec": 0.6,
        "evaluated_stints": 10,
    }
    (directory / "temporal-production.json").write_text(json.dumps(report))
    rows = historical_validation(tmp_path, "current")
    assert rows[0]["status"] == "Not evaluated for this snapshot"
    assert rows[0]["evaluated_snapshot"] == "old-version"
    assert "1.200" in rows[0]["result"]
    assert rows[1]["result"] == "Evaluation artifact unavailable"
    assert rows[1]["report_date"] is None
    assert historical_validation(tmp_path, "old")[0]["status"] == "Evaluated on this snapshot"


def test_structural_failures_are_not_published_as_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scripts.export_audit_evidence.check_metrics", lambda _: {"bad": 1})
    monkeypatch.setattr("scripts.export_audit_evidence.check_robustness", lambda _: {"good": 0})
    with duckdb.connect() as c, pytest.raises(ValueError, match="publication checks failed"):
        structural_validation(c, {"version": "v", "sha256": "hash"})


def test_readme_uses_export_counts_and_preserves_surrounding_text(tmp_path: Path) -> None:
    artifact = tmp_path / "evidence.parquet"
    with duckdb.connect() as c:
        c.execute("create table evidence(dataset varchar,payload varchar,snapshot_version varchar)")
        c.execute(
            "insert into evidence values ('dataset_statistics',?,'test-version')",
            [json.dumps([{"dataset": "Replay", "observations": 12345, "races": 6}])],
        )
        c.execute("copy evidence to ? (format parquet)", [str(artifact)])
    readme = tmp_path / "README.md"
    readme.write_text(
        "Before\n<!-- audit-statistics:start -->old<!-- audit-statistics:end -->\nAfter"
    )
    update_readme(artifact, readme)
    assert "| Replay | 12,345 | 6 |" in readme.read_text()
    assert readme.read_text().startswith("Before\n")
    assert readme.read_text().endswith("\nAfter")
    assert "test-version" in readme_statistics(artifact)


def test_successful_export_is_atomic_and_serving_rejects_wrong_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = tmp_path / "latest.duckdb"
    with duckdb.connect(str(snapshot)) as c:
        c.execute(
            "create schema dashboard; create table dashboard.snapshot_metadata as select 'v1' as version"
        )
    snapshot.with_suffix(".json").write_text(
        json.dumps({"version": "v1", "sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest()})
    )
    monkeypatch.setattr("scripts.export_audit_evidence.evidence_summary", lambda _: [])
    monkeypatch.setattr(
        "scripts.export_audit_evidence.dataset_statistics",
        lambda _: [{"dataset": "Replay", "observations": 12, "races": 1}],
    )
    monkeypatch.setattr("scripts.export_audit_evidence.structural_validation", lambda *_: {})
    artifact = tmp_path / "evidence.parquet"
    export(snapshot, artifact)
    sql = (
        Path("dashboard/sources/f1/dataset_statistics.sql")
        .read_text()
        .replace("../data/dashboard/audit-evidence.parquet", str(artifact))
    )
    with duckdb.connect(str(snapshot), read_only=True) as c:
        assert c.execute(sql).fetchall()[0][:3] == ("Replay", 12, 1)
    with duckdb.connect(str(snapshot)) as c:
        c.execute("update dashboard.snapshot_metadata set version='v2'")
        with pytest.raises(duckdb.Error, match="stale"):
            c.execute(sql).fetchall()
    previous = artifact.read_bytes()
    with pytest.raises(ValueError, match="checksum"):
        export(snapshot, artifact)
    assert artifact.read_bytes() == previous
