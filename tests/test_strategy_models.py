"""Regression tests run the actual dbt SQL on focused source fixtures."""
import re
from pathlib import Path

import duckdb


def model(name):
    sql = Path(f"warehouse/dbt/models/marts/{name}.sql").read_text(encoding="utf-8")
    return re.sub(r"\{\{ ref\('([^']+)'\) \}\}", r"\1", sql)


def test_pit_visits_survive_missing_position_windows():
    with duckdb.connect() as c:
        c.execute("create table stg_pitstops as select 2026 season, 14 round, 'a' driver_id, 1 stop_number, 1 pit_lap, 22.0 duration_sec")
        c.execute("create table stg_laps as select 2026 season, 14 round, 'AAA' driver_code, 1 lap_number, 5 position, 'R' session")
        c.execute("create table stg_driver_codes as select 2026 season, 'AAA' driver_code, 'a' driver_id, 'A' driver_name")
        c.execute("create table stg_races as select 2026 season, 14 round, 'Madrid' race_name")
        result = c.execute(model('mart_pit_strategy')).fetchdf()
        assert len(result) == 1
        assert result.positions_gained.isna().all()


def test_rain_outside_lap_window_does_not_make_dry_laps_wet():
    with duckdb.connect() as c:
        c.execute("create table mart_lap_times as select 2026 season, 14 round, 'Madrid' race_name, 'AAA' driver_code, i lap_number, 'MEDIUM' compound, i tyre_life, 90.0 lap_time_sec from range(2,12) t(i)")
        c.execute("create table stg_laps as select *, 1000.0 + lap_number * 90 lap_start_sec, 'R' session from mart_lap_times")
        c.execute("create table stg_weather as select 2026 season, 14 round, 'R' session, 1000.0+i*90+1 time_sec, 35.0 track_temp, 20.0 air_temp, false is_raining from range(2,12) t(i)")
        c.execute("insert into stg_weather values (2026,14,'R',500,20,15,true)")
        result = c.execute(model('mart_weather_degradation')).fetchdf()
        assert result.weather_bucket.tolist() == ['cool']
        assert result.n_laps.tolist() == [10]
        c.execute('delete from stg_weather')
        assert c.execute(model('mart_weather_degradation')).fetchdf().weather_bucket.isna().all()
