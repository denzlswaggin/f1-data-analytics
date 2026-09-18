"""Execute the page queries against controlled timing and published peer evidence."""
import re
from pathlib import Path

import duckdb

PAGE = Path(__file__).parents[1] / "dashboard/pages/race-pace.md"


def test_shared_baseline_and_historical_timing_scope() -> None:
    queries = dict(re.findall(r"```sql (\w+)\n(.*?)```", PAGE.read_text(encoding="utf-8"), re.S))
    with duckdb.connect() as db:
        db.execute("create schema f1")
        db.execute("create table f1.lap_times (season int, round int, race_name varchar, "
                   "driver_code varchar, lap_number int, compound varchar, lap_time_sec double)")
        db.execute("insert into f1.lap_times values (2022, 1, 'Historical', 'AAA', 20, 'HARD', 90)")
        db.execute("insert into f1.lap_times select 2026, 14, 'Madrid', 'AAA', "
                   "range, 'HARD', 90 from range(1, 21)")
        db.execute("create table f1.traffic_adjusted_laps (season int, round int, "
                   "driver_code varchar, lap_number int, compound varchar, controlled_pace_delta_sec double)")
        db.execute("insert into f1.traffic_adjusted_laps select 2026, 14, 'AAA', "
                   "range, 'HARD', -0.321 from range(2, 15)")
        for season, race_round in ((2026, 14), (2022, 1)):
            for name in ("races", "comparable_laps", "race_laps", "phase_pace", "compound_pace"):
                sql = queries[name]
                for key, value in {"season": season, "race": race_round,
                                   "driver_a": "AAA", "driver_b": "BBB"}.items():
                    sql = sql.replace("${inputs." + key + ".value}", str(value))
                sql = sql.replace("${comparable_laps}", "comparable_laps")
                db.execute(f"create or replace temp table {name} as {sql}")
            assert db.execute("select count(*) from races").fetchone()[0] == 1
            assert db.execute("select count(*) from compound_pace").fetchone()[0] == 1
            rows = db.execute("select controlled_delta_sec from race_laps").fetchall()
            if season == 2026:
                assert len(rows) == 13
                assert all(row[0] == -0.321 for row in rows)
                # Four opening laps fail the five-lap publication minimum.
                assert db.execute("select race_phase, comparable_laps from phase_pace").fetchall() == [("Middle", 9)]
            else:
                assert rows == []
                assert db.execute("select count(*) from phase_pace").fetchone()[0] == 0
