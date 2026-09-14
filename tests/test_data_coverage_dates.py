"""Coverage freshness follows each analysis's actual evidence races."""

import datetime as dt
import shutil
from pathlib import Path

import duckdb
import pytest

QUERY = Path("dashboard/sources/f1/data_coverage.sql").read_text()


@pytest.mark.parametrize("scenario", ["unrelated_new_laps", "older_qualifying_only"])
def test_global_dates_do_not_borrow_other_analyses(tmp_path: Path, scenario: str) -> None:
    snapshot = tmp_path / "coverage.duckdb"
    shutil.copyfile("tests/fixtures/dashboard-ci.duckdb", snapshot)
    with duckdb.connect(str(snapshot)) as conn:
        date = "2026-12-31" if scenario == "unrelated_new_laps" else "2026-01-01"
        conn.execute(
            """
            insert into staging.stg_races by name
            select * replace (99 as round, cast(? as date) as race_date)
            from staging.stg_races limit 1
        """,
            [date],
        )
        if scenario == "unrelated_new_laps":
            conn.execute("""
                insert into marts.mart_lap_times by name
                select * replace (99 as round) from marts.mart_lap_times limit 1
            """)
        else:
            conn.execute("update intermediate.int_teammate_quali_gaps set round=99")
        rows = conn.sql(QUERY).df().set_index("section")
        assert rows.loc["driver_rating", "latest_event_date"].date() == (
            dt.date(2026, 8, 23) if scenario == "unrelated_new_laps" else dt.date(2026, 1, 1)
        )
        for section in ("pace_profile", "weather_slope"):
            assert rows.loc[section, "latest_event_date"].date() == dt.date(2026, 8, 23)
