"""PostgreSQL maintenance tests that never contact a database."""

from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path
from typing import cast

import pytest
from ingestion.config import Settings
from ingestion.maintenance import _verify_backup, create_postgres_backup, latest_postgres_backup


def _postgres_settings() -> Settings:
    return Settings(
        warehouse="postgres",
        pg_host="db.internal",
        pg_user="backup_user",
        pg_password="do-not-leak",
        pg_database="f1",
    )


def test_backup_is_atomic_and_writes_checksum_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def fake_run(
        command: list[str], *, check: bool, env: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["password"] = env["PGPASSWORD"]
        Path(command[command.index("--file") + 1]).write_bytes(b"portable database dump")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    backup = create_postgres_backup(
        tmp_path,
        _postgres_settings(),
        now=dt.datetime(2026, 8, 30, 12, tzinfo=dt.UTC),
    )

    assert backup.name == "f1-20260830T120000Z.dump"
    assert backup.read_bytes() == b"portable database dump"
    assert not backup.with_suffix(".dump.partial").exists()
    manifest = json.loads(backup.with_suffix(".dump.json").read_text(encoding="utf-8"))
    assert manifest["bytes"] == len(b"portable database dump")
    assert "do-not-leak" not in " ".join(cast(list[str], captured["command"]))
    assert captured["password"] == "do-not-leak"
    _verify_backup(backup)


def test_backup_verification_rejects_tampering(tmp_path: Path) -> None:
    backup = tmp_path / "backup.dump"
    backup.write_bytes(b"tampered")
    backup.with_suffix(".dump.json").write_text(
        json.dumps({"file": backup.name, "sha256": "wrong"}), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="does not match"):
        _verify_backup(backup)


def test_latest_backup_uses_timestamped_filename_order(tmp_path: Path) -> None:
    older = tmp_path / "f1-20260801T120000Z.dump"
    newer = tmp_path / "f1-20260830T120000Z.dump"
    older.write_bytes(b"old")
    newer.write_bytes(b"new")

    assert latest_postgres_backup(tmp_path) == newer
