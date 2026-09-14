"""Serving regressions: missing evidence cannot become a result or a zero."""

from pathlib import Path

import duckdb
import pytest
from ingestion.dashboard_snapshot import validate_recorded_story
from jinja2 import Environment


def connection() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    conn.execute("""
        create schema staging; create schema marts;
        create table staging.stg_results as
        select 2025 season, 1 as round, code driver_code, code driver_id,
            code driver_name, 'team' constructor_id, grid grid_position,
            finish finish_position, cast(finish as varchar) position_text,
            'Finished' status, true is_classified
        from (values ('AAA',1,1), ('BBB',0,2), ('CCC',3,3)) t(code,grid,finish);
        create table staging.stg_races as select 2025 season, 1 as round, 'Race' race_name;
        create table marts.mart_lap_times as select 2025 season, 1 as round;
        create table marts.traffic_adjusted_laps as
        select 2025 season, 1 as round, code driver_code,
            cast(delta as double) controlled_pace_delta_sec
        from (values ('AAA',-1), ('BBB',1)) t(code,delta), range(5);
        create table marts.mart_pit_strategy (
            season integer, round integer, driver_id varchar);
        create table marts.racecraft_processing (season integer, round integer);
        create table marts.race_replay (
            season integer, round integer, driver_code varchar,
            running_order integer, t_s double);
        create table marts.race_overtakes (
            season integer, round integer, passer_code varchar, passed_code varchar);
    """)
    return conn


def test_all_results_survive_missing_pace_and_pass_analysis() -> None:
    with connection() as conn:
        frame = conn.execute(Path("dashboard/sources/f1/race_story.sql").read_text()).fetchdf()
    assert len(frame) == 3
    assert frame["passes_made"].isna().all()
    assert frame["stops"].isna().all()
    assert frame["outcome_vs_pace"].isna().all()  # partial cohort != full-field rank
    assert frame.loc[frame.driver_code == "CCC", "pace_rank"].isna().all()
    assert frame.loc[frame.driver_code == "BBB", "grid_gain"].isna().all()  # pit-lane grid 0


def test_processed_zero_requires_driver_order_and_full_pace_field_for_rank_delta() -> None:
    with connection() as conn:
        conn.execute("""
            insert into marts.racecraft_processing values (2025,1);
            insert into marts.race_replay values (2025,1,'AAA',1,0), (2025,1,'BBB',null,0);
            insert into marts.traffic_adjusted_laps
                select 2025,1,'CCC',2 from range(5);
            insert into marts.mart_pit_strategy values (2025,1,'AAA'), (2025,1,'AAA');
        """)
        frame = conn.execute(Path("dashboard/sources/f1/race_story.sql").read_text()).fetchdf()
    assert frame.loc[frame.driver_code == "AAA", "passes_made"].iloc[0] == 0
    assert frame.loc[frame.driver_code != "AAA", "passes_made"].isna().all()
    assert frame["pace_field_complete"].all()
    assert frame["outcome_vs_pace"].tolist() == [0, 0, 0]
    assert frame["stops"].tolist() == [2, 0, 0]


def test_dbt_result_table_preserves_results_without_retired_model() -> None:
    template = Path("warehouse/dbt/models/marts/mart_race_story.sql").read_text()
    sql = (
        Environment()
        .from_string(template)
        .render(ref=lambda name: f"{'staging' if name.startswith('stg_') else 'marts'}.{name}")
    )
    with connection() as conn:
        conn.execute("create table staging.stg_pitstops as select * from marts.mart_pit_strategy")
        conn.execute("insert into staging.stg_pitstops values (2025,1,'AAA'), (2025,1,'AAA')")
        conn.execute("create table marts.mart_race_story as " + sql)
        validate_recorded_story(conn)
        frame = conn.sql("select * from marts.mart_race_story order by finish_position").fetchdf()
        assert len(frame) == 3
        assert frame["pace_rank"].isna().all()
        assert frame["stops"].tolist() == [2, 0, 0]
        assert frame.loc[frame.driver_code == "BBB", "grid_gain"].isna().all()
        conn.execute("update marts.mart_race_story set finish_position=99 where driver_code='AAA'")
        with pytest.raises(ValueError, match="does not match"):
            validate_recorded_story(conn)
        conn.execute("update marts.mart_race_story set finish_position=1 where driver_code='AAA'")
        conn.execute("update marts.mart_race_story set pace_rank=1 where driver_code='AAA'")
        with pytest.raises(ValueError, match="Retired race-story"):
            validate_recorded_story(conn)
