"""Pit provenance is rebuilt from full staging, including incremental corrections."""

from pathlib import Path

import duckdb
import pandas as pd
from analytics.pipeline import build_all_pit_lap_context, build_pit_lap_context_incremental
from ingestion.config import Settings
from ingestion.loaders.warehouse import read_query


def test_full_incremental_parity_and_empty_partition_correction(tmp_path: Path) -> None:
    settings = Settings(warehouse="duckdb", duckdb_path=tmp_path / "pits.duckdb")
    with duckdb.connect(str(settings.duckdb_path)) as connection:
        connection.execute("create schema staging")
        connection.execute(
            "create table staging.stg_laps as "
            "select 2025 season, r.round, 'RUS' driver_code, lap_number, 1 stint, 'R' as session "
            "from (values (8), (9)) r(round) cross join range(60, 66) l(lap_number)"
        )
        connection.execute(
            "create table staging.stg_driver_codes as "
            "select 2025 season, 'russell' driver_id, 'RUS' driver_code"
        )
        connection.execute(
            "create table staging.stg_pitstops as "
            "select 2025 season, 8 round, 'russell' driver_id, 62 pit_lap, 25.063 duration_sec"
        )
    full = build_all_pit_lap_context(settings)
    expected = full.loc[full["round"].eq(8)].reset_index(drop=True)
    actual = build_pit_lap_context_incremental(2025, 8, settings)
    pd.testing.assert_frame_equal(actual, expected)
    assert actual.loc[actual["is_pit_boundary"], "lap_number"].tolist() == [62, 63]
    assert actual.loc[actual["is_pit_boundary"], "pit_context_source"].eq("jolpica").all()

    with duckdb.connect(str(settings.duckdb_path)) as connection:
        connection.execute("delete from staging.stg_laps where round = 8")
    assert build_pit_lap_context_incremental(2025, 8, settings).empty
    persisted = read_query("select * from marts.pit_lap_context order by lap_number", settings)
    pd.testing.assert_frame_equal(
        persisted, full.loc[full["round"].eq(9)].reset_index(drop=True), check_dtype=False
    )
