import json
import subprocess
import sys
from pathlib import Path

import duckdb
from scripts.audit_race_control_coverage import _source_marker, audit_races

FIXTURE = Path("tests/fixtures/dashboard-ci.duckdb")


def test_source_marker_is_independent_and_strict() -> None:
    assert _source_marker("VIRTUAL SAFETY CAR DEPLOYED", None) == ("VSC", "start")
    assert _source_marker("SAFETY CAR IN THIS LAP", None) == ("Safety Car", "end")
    assert _source_marker("RED FLAG - RACE SUSPENDED", None) == ("Red Flag", "start")
    assert _source_marker("SAFETY CAR INFRINGEMENT", None) is None


def test_ci_race_reconciles_every_source_deployment_to_the_mart() -> None:
    with duckdb.connect(str(FIXTURE), read_only=True) as connection:
        audit = audit_races(connection, 2026, 2026)

    assert audit["summary"]["audit_pass"]
    assert audit["summary"]["audited_races"] == 1
    assert audit["summary"]["source_start_markers"] == 3
    assert audit["summary"]["modelled_events"] == 3
    assert audit["summary"]["structural_violations"] == 0
    assert all(not race["violations"] for race in audit["races"])


def test_check_report_accepts_exact_report_and_rejects_drift(tmp_path: Path) -> None:
    with duckdb.connect(str(FIXTURE), read_only=True) as connection:
        audit = audit_races(connection, 2026, 2026)
    report = tmp_path / "audit.json"
    report.write_text(json.dumps(audit, indent=2, ensure_ascii=False, default=str) + "\n")
    command = [
        sys.executable,
        "scripts/audit_race_control_coverage.py",
        str(FIXTURE),
        "--from-season",
        "2026",
        "--to-season",
        "2026",
        "--check-report",
        str(report),
        "--summary-only",
    ]

    assert subprocess.run(command, capture_output=True, text=True, check=False).returncode == 0
    report.write_text("{}\n", encoding="utf-8")
    failed = subprocess.run(command, capture_output=True, text=True, check=False)
    assert failed.returncode != 0
    assert "frozen race-control audit report is stale" in failed.stderr


def test_validation_document_total_matches_frozen_audit() -> None:
    report = json.loads(Path("validation/race-control-2024-2026-audit-v1.json").read_text())
    document = Path("docs/race-control-2024-2026-validation.md").read_text()
    counts = report["summary"]["status_counts"]
    expected_row = (
        f"| **Total** | **{report['summary']['audited_races']}** | **6,865** | "
        f"**{report['summary']['modelled_events']}** | "
        f"**{counts['verified_all_components']}** | "
        f"**{counts['verified_with_withheld_components']}** | "
        f"**{counts['verified_no_neutralisation_marker']}** | "
        f"**{counts['verified_source_limited']}** |"
    )
    assert expected_row in document
