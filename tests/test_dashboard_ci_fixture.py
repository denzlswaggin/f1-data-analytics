from pathlib import Path

import duckdb
from ingestion.dashboard_snapshot import validate_dashboard_snapshot

FIXTURE = Path("tests/fixtures/dashboard-ci.duckdb")


def test_dashboard_ci_fixture_covers_contract_without_raw_position_payload() -> None:
    assert validate_dashboard_snapshot(FIXTURE) == "2026-08-23"
    with duckdb.connect(str(FIXTURE), read_only=True) as connection:
        assert connection.execute(
            "select count(*) from information_schema.tables "
            "where table_schema = 'staging' and table_name = 'stg_positions'"
        ).fetchone() == (0,)
        assert connection.execute(
            "select count(distinct season || '-' || round) from marts.mart_lap_times"
        ).fetchone() == (1,)
