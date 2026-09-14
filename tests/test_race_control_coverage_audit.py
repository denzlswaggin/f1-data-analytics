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
