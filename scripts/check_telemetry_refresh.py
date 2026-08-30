"""Regression check that an incremental dbt run applies a late telemetry correction.

This script is intended for the disposable DuckDB fixture warehouse in CI. It
changes one raw telemetry value, reruns only ``mart_lap_telemetry``, and verifies
that the serving mart reflects the correction without changing partition size.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import duckdb


def main() -> None:
    warehouse = Path(os.getenv("F1_DUCKDB_PATH", "data/warehouse/f1.duckdb"))
    key_columns = "season, round, session, driver_code, lap_number, distance_m"

    with duckdb.connect(str(warehouse)) as connection:
        key = connection.execute(
            f"select {key_columns}, speed_kph from raw.telemetry order by {key_columns} limit 1"
        ).fetchone()
        if key is None:
            raise SystemExit("raw.telemetry has no fixture row")
        season, round_, session, driver, lap, distance, old_speed = key
        before_count = connection.execute(
            "select count(*) from marts.mart_lap_telemetry where season = ? and round = ?",
            [season, round_],
        ).fetchone()[0]
        new_speed = float(old_speed) + 1.0
        connection.execute(
            "update raw.telemetry set speed_kph = ? "
            "where season = ? and round = ? and session = ? and driver_code = ? "
            "and lap_number = ? and distance_m = ?",
            [new_speed, season, round_, session, driver, lap, distance],
        )
        connection.execute(
            """
            create table if not exists raw.ingestion_partitions (
                resource varchar, season integer, round integer, session varchar,
                loaded_at timestamp, load_id varchar, row_count bigint
            )
            """
        )
        connection.execute(
            "delete from raw.ingestion_partitions "
            "where resource = 'telemetry' and season = ? and round = ? and session = ?",
            [season, round_, session],
        )
        connection.execute(
            "insert into raw.ingestion_partitions "
            "select 'telemetry', ?, ?, ?, current_timestamp, 'late-correction-check', count(*) "
            "from raw.telemetry where season = ? and round = ? and session = ?",
            [season, round_, session, season, round_, session],
        )

    refresh_started = time.perf_counter()
    subprocess.run(
        [
            "dbt",
            "run",
            "--select",
            "mart_lap_telemetry",
            "--project-dir",
            "warehouse/dbt",
            "--profiles-dir",
            "warehouse/dbt",
            "--target",
            "dev",
        ],
        check=True,
    )
    refresh_seconds = time.perf_counter() - refresh_started
    max_refresh_seconds = float(os.getenv("F1_TELEMETRY_REFRESH_MAX_SECONDS", "30"))
    if refresh_seconds > max_refresh_seconds:
        raise SystemExit(
            f"telemetry refresh took {refresh_seconds:.2f}s (limit: {max_refresh_seconds:.2f}s)"
        )

    with duckdb.connect(str(warehouse), read_only=True) as connection:
        refreshed = connection.execute(
            "select speed_kph from marts.mart_lap_telemetry "
            "where season = ? and round = ? and driver_code = ? "
            "and lap_number = ? and distance_m = ?",
            [season, round_, driver, lap, distance],
        ).fetchone()
        after_count = connection.execute(
            "select count(*) from marts.mart_lap_telemetry where season = ? and round = ?",
            [season, round_],
        ).fetchone()[0]

    if refreshed is None or abs(float(refreshed[0]) - new_speed) > 1e-9:
        raise SystemExit("late telemetry correction was not propagated")
    if after_count != before_count:
        raise SystemExit(f"telemetry partition size changed: {before_count} -> {after_count}")
    print(
        f"PASS telemetry correction: {old_speed} -> {new_speed} "
        f"({after_count} rows, {refresh_seconds:.2f}s)"
    )


if __name__ == "__main__":
    main()
