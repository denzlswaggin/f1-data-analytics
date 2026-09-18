import re
from pathlib import Path

import duckdb
import pytest

PAGE = Path(__file__).parents[1] / "dashboard/pages/telemetry.md"


@pytest.mark.parametrize(
    "lap_b,age_b,compound_b,status_b,expected",
    [
        (31, 5, "HARD", "1", 1),
        (34, 5, "HARD", "1", 0),
        (31, 9, "HARD", "1", 0),
        (31, 5, "WET", "1", 0),
        (31, 5, "HARD", "4", 0),
    ],
)
def test_duel_uses_jointly_matched_laps(
    lap_b: int, age_b: int, compound_b: str, status_b: str, expected: int
) -> None:
    queries = dict(re.findall(r"```sql (\w+)\n(.*?)```", PAGE.read_text(encoding="utf-8"), re.S))
    with duckdb.connect() as db:
        db.execute("create schema f1")
        db.execute("""create table f1.telemetry_laps as
            select 2026 as season, 14 as round, 'AAA' as driver_code,
                10 as lap_number, 'SOFT' as compound, 5 as tyre_life,
                '1' as track_status, 88.0::double as lap_time_sec,
                null::double as pit_in_time_sec, null::double as pit_out_time_sec,
                range * 25.0 as distance_m, 200.0::double as speed_kph
            from range(120)""")
        db.execute(
            "insert into f1.telemetry_laps select * replace (30 as lap_number, "
            "'HARD' as compound, 90.0 as lap_time_sec) from f1.telemetry_laps"
        )
        db.execute(
            "insert into f1.telemetry_laps select * replace ('BBB' as driver_code, "
            "? as lap_number, ? as tyre_life, ? as compound, ? as track_status, "
            "89.0 as lap_time_sec, 180.0 as speed_kph) from f1.telemetry_laps where lap_number = 30",
            [lap_b, age_b, compound_b, status_b],
        )
        for name in ("candidate_laps", "matched_pair", "selected_telemetry", "time_delta"):
            sql = queries[name]
            for key, value in {
                "season": 2026,
                "race": 14,
                "driver_a": "AAA",
                "driver_b": "BBB",
            }.items():
                sql = sql.replace("${inputs." + key + ".value}", str(value))
            for dependency in ("candidate_laps", "matched_pair", "selected_telemetry"):
                sql = sql.replace("${" + dependency + "}", dependency)
            db.execute(f"create temp table {name} as {sql}")
        assert db.execute("select count(*) from matched_pair").fetchall()[0][0] == expected
        if expected:
            assert db.execute("select lap_a, lap_b from matched_pair").fetchone() == (30, 31)
            delta = db.execute(
                "select delta_sec from time_delta order by distance_m desc limit 1"
            ).fetchall()[0][0]
            assert delta == pytest.approx(2975 / 50 - 2975 / (200 / 3.6))
        else:
            assert db.execute("select count(*) from selected_telemetry").fetchall()[0][0] == 0
            assert db.execute("select count(*) from time_delta").fetchall()[0][0] == 0
