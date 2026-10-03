"""Load DataFrames into the raw schema of the warehouse (DuckDB or Postgres).

Loading is idempotent: by default a whole season's rows are deleted and
re-inserted, so re-running a backfill never duplicates data. Per-round sources
can instead pass ``replace_rounds=True`` to delete-and-replace only the rounds
present in the frame, which lets an incremental run append *new* rounds without
wiping the rounds already loaded. The target is chosen by ``settings.warehouse``
so the same ingestion code serves dev (DuckDB) and prod (Postgres).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import uuid4

import duckdb
import pandas as pd
from pandas.api import types as pandas_types
from sqlalchemy import bindparam, create_engine, text

from ingestion.config import Settings, get_settings
from ingestion.logging import get_logger

log = get_logger(__name__)
_ADDITIVE_RAW_TABLES = {
    "openf1_positions",
    "openf1_intervals",
    "openf1_race_control",
    "openf1_timing_audit",
}


def _portable_sql_type(series: pd.Series) -> str:
    """Return a conservative DuckDB/Postgres type for additive mart columns."""
    dtype = series.dtype
    if pandas_types.is_bool_dtype(dtype):
        return "BOOLEAN"
    if pandas_types.is_integer_dtype(dtype):
        return "BIGINT"
    if pandas_types.is_float_dtype(dtype):
        return "DOUBLE PRECISION"
    if pandas_types.is_datetime64_any_dtype(dtype):
        return "TIMESTAMP WITH TIME ZONE"
    return "VARCHAR"


def _add_missing_frame_columns(
    connection: duckdb.DuckDBPyConnection, schema: str, table: str, frame: pd.DataFrame
) -> None:
    """Make additive DataFrame schema evolution safe for incremental writers."""
    for column in frame.columns:
        sql_type = _portable_sql_type(frame[column])
        statement = (
            f'ALTER TABLE "{schema}"."{table}" ADD COLUMN IF NOT EXISTS "{column}" {sql_type}'
        )
        connection.execute(statement)


@dataclass(frozen=True)
class PartitionLoad:
    """Audit record for one warehouse partition replaced by an ingest run."""

    resource: str
    season: int
    round: int | None
    session: str | None
    loaded_at: dt.datetime
    load_id: str
    row_count: int


def _partition_loads(
    df: pd.DataFrame, table: str, season: int, replace_rounds: bool
) -> list[PartitionLoad]:
    """Describe the physical partitions touched by a warehouse load."""
    loaded_at = dt.datetime.now(dt.UTC)
    load_id = uuid4().hex
    if not replace_rounds or "round" not in df.columns:
        return [PartitionLoad(table, season, None, None, loaded_at, load_id, len(df))]

    group_columns = ["round"] + (["session"] if "session" in df.columns else [])
    loads: list[PartitionLoad] = []
    grouper: str | list[str] = group_columns[0] if len(group_columns) == 1 else group_columns
    for values, frame in df.groupby(grouper, sort=True, dropna=False):
        value_tuple = values if isinstance(values, tuple) else (values,)
        session = str(value_tuple[1]) if len(value_tuple) == 2 else None
        loads.append(
            PartitionLoad(
                table, season, int(value_tuple[0]), session, loaded_at, load_id, len(frame)
            )
        )
    return loads


def load_dataframe(
    df: pd.DataFrame,
    table: str,
    season: int,
    settings: Settings | None = None,
    *,
    replace_rounds: bool = False,
) -> int:
    """Load ``df`` into ``raw.<table>`` for the given season. Returns row count.

    By default the whole season is replaced (delete-then-insert). With
    ``replace_rounds=True`` only the rounds present in ``df`` are replaced, so an
    incremental run can append new rounds without deleting the rounds already
    loaded. ``replace_rounds`` is ignored if the frame has no ``round`` column.
    """
    settings = settings or get_settings()
    if df.empty:
        log.warning("warehouse.skip_empty", table=table, season=season)
        return 0

    by_round = replace_rounds and "round" in df.columns
    rounds = sorted({int(r) for r in df["round"].dropna().unique()}) if by_round else []
    partition_loads = _partition_loads(df, table, season, replace_rounds)

    if settings.warehouse == "duckdb":
        _load_duckdb(df, table, season, settings, rounds if by_round else None, partition_loads)
    else:
        _load_postgres(df, table, season, settings, rounds if by_round else None, partition_loads)

    log.info(
        "warehouse.load",
        target=settings.warehouse,
        table=table,
        season=season,
        rows=len(df),
        rounds=rounds if by_round else None,
    )
    return len(df)


def _load_duckdb(
    df: pd.DataFrame,
    table: str,
    season: int,
    settings: Settings,
    rounds: list[int] | None,
    partition_loads: list[PartitionLoad],
) -> None:
    settings.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(settings.duckdb_path))
    try:
        con.register("incoming", df)
        con.execute("BEGIN TRANSACTION")
        con.execute("CREATE SCHEMA IF NOT EXISTS raw")
        # Create the table from the incoming shape if it doesn't exist yet.
        con.execute(
            f'CREATE TABLE IF NOT EXISTS raw."{table}" AS SELECT * FROM incoming WHERE 1 = 0'
        )
        if table in _ADDITIVE_RAW_TABLES:
            _add_missing_frame_columns(con, "raw", table, df)
        if table == "laps":
            for column in ("pit_in_time_sec", "pit_out_time_sec"):
                con.execute(f'ALTER TABLE raw."laps" ADD COLUMN IF NOT EXISTS {column} DOUBLE')
        if rounds is not None and "session" in df.columns:
            for load in partition_loads:
                con.execute(
                    f'DELETE FROM raw."{table}" WHERE season = ? AND round = ? '
                    "AND session IS NOT DISTINCT FROM ?",
                    [season, load.round, load.session],
                )
        elif rounds is not None:
            placeholders = ", ".join("?" for _ in rounds)
            con.execute(
                f'DELETE FROM raw."{table}" WHERE season = ? AND round IN ({placeholders})',
                [season, *rounds],
            )
        else:
            con.execute(f'DELETE FROM raw."{table}" WHERE season = ?', [season])
        # Match by column name, not DataFrame order. External APIs can reorder
        # fields without changing their schema; positional inserts would silently
        # cast values into the wrong destination columns.
        con.execute(f'INSERT INTO raw."{table}" BY NAME SELECT * FROM incoming')
        _ensure_duckdb_ingestion_audit(con)
        for load in partition_loads:
            con.execute(
                "DELETE FROM raw.ingestion_partitions "
                "WHERE resource = ? AND season = ? "
                "AND round IS NOT DISTINCT FROM ? AND session IS NOT DISTINCT FROM ?",
                [load.resource, load.season, load.round, load.session],
            )
            con.execute(
                "INSERT INTO raw.ingestion_partitions VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    load.resource,
                    load.season,
                    load.round,
                    load.session,
                    load.loaded_at,
                    load.load_id,
                    load.row_count,
                ],
            )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.unregister("incoming")
        con.close()


def _ensure_duckdb_ingestion_audit(con: duckdb.DuckDBPyConnection) -> None:
    """Create the audit table and migrate legacy timezone-naive timestamps."""
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS raw.ingestion_partitions (
            resource VARCHAR,
            season INTEGER,
            round INTEGER,
            session VARCHAR,
            loaded_at TIMESTAMPTZ,
            load_id VARCHAR,
            row_count BIGINT
        )
        """
    )
    loaded_at_type = con.execute(
        "select data_type from information_schema.columns "
        "where table_schema = 'raw' and table_name = 'ingestion_partitions' "
        "and column_name = 'loaded_at'"
    ).fetchone()
    if loaded_at_type is not None and loaded_at_type[0] == "TIMESTAMP":
        con.execute(
            "alter table raw.ingestion_partitions alter loaded_at type timestamptz "
            "using loaded_at at time zone current_setting('TimeZone')"
        )


def _load_postgres(
    df: pd.DataFrame,
    table: str,
    season: int,
    settings: Settings,
    rounds: list[int] | None,
    partition_loads: list[PartitionLoad],
) -> None:
    engine = create_engine(settings.pg_dsn)
    schema = settings.pg_schema
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            # head(0) append creates the table if missing, else no-op.
            df.head(0).to_sql(table, conn, schema=schema, if_exists="append", index=False)
            if table in _ADDITIVE_RAW_TABLES:
                for column in df.columns:
                    sql_type = _portable_sql_type(df[column])
                    conn.exec_driver_sql(
                        f'ALTER TABLE "{schema}"."{table}" ADD COLUMN IF NOT EXISTS '
                        f'"{column}" {sql_type}'
                    )
            if table == "laps":
                for column in ("pit_in_time_sec", "pit_out_time_sec"):
                    conn.exec_driver_sql(
                        f'ALTER TABLE "{schema}"."laps" '
                        f"ADD COLUMN IF NOT EXISTS {column} DOUBLE PRECISION"
                    )
            if rounds is not None and "session" in df.columns:
                for load in partition_loads:
                    conn.execute(
                        text(
                            f'DELETE FROM "{schema}"."{table}" '
                            "WHERE season = :season AND round = :round "
                            "AND session IS NOT DISTINCT FROM :session"
                        ),
                        {"season": season, "round": load.round, "session": load.session},
                    )
            elif rounds is not None:
                conn.execute(
                    text(
                        f'DELETE FROM "{schema}"."{table}" '
                        "WHERE season = :season AND round IN :rounds"
                    ).bindparams(bindparam("rounds", expanding=True)),
                    {"season": season, "rounds": rounds},
                )
            else:
                conn.execute(
                    text(f'DELETE FROM "{schema}"."{table}" WHERE season = :season'),
                    {"season": season},
                )
            df.to_sql(table, conn, schema=schema, if_exists="append", index=False)
            conn.exec_driver_sql(
                f"""
                CREATE TABLE IF NOT EXISTS "{schema}".ingestion_partitions (
                    resource VARCHAR NOT NULL,
                    season INTEGER NOT NULL,
                    round INTEGER,
                    session VARCHAR,
                    loaded_at TIMESTAMPTZ NOT NULL,
                    load_id VARCHAR NOT NULL,
                    row_count BIGINT NOT NULL
                )
                """
            )
            for load in partition_loads:
                conn.execute(
                    text(
                        f'DELETE FROM "{schema}".ingestion_partitions '
                        "WHERE resource = :resource AND season = :season "
                        "AND round IS NOT DISTINCT FROM :round "
                        "AND session IS NOT DISTINCT FROM :session"
                    ),
                    {
                        "resource": load.resource,
                        "season": load.season,
                        "round": load.round,
                        "session": load.session,
                    },
                )
                conn.execute(
                    text(
                        f'INSERT INTO "{schema}".ingestion_partitions '
                        "(resource, season, round, session, loaded_at, load_id, row_count) "
                        "VALUES (:resource, :season, :round, :session, :loaded_at, :load_id, :row_count)"
                    ),
                    {
                        "resource": load.resource,
                        "season": load.season,
                        "round": load.round,
                        "session": load.session,
                        "loaded_at": load.loaded_at,
                        "load_id": load.load_id,
                        "row_count": load.row_count,
                    },
                )
    finally:
        engine.dispose()


def read_query(sql: str, settings: Settings | None = None) -> pd.DataFrame:
    """Run a read-only SQL query against the active warehouse and return a frame."""
    settings = settings or get_settings()
    if settings.warehouse == "duckdb":
        con = duckdb.connect(str(settings.duckdb_path), read_only=True)
        try:
            return con.execute(sql).fetchdf()
        finally:
            con.close()
    engine = create_engine(settings.pg_dsn)
    try:
        return pd.read_sql_query(text(sql), engine)
    finally:
        engine.dispose()


def latest_loaded_round(table: str, season: int, settings: Settings | None = None) -> int:
    """Return the highest ``round`` already loaded for ``raw.<table>`` in ``season``.

    The incremental high-watermark: a per-round ingest can start from
    ``latest_loaded_round + 1`` to fetch only rounds it hasn't loaded yet.
    Returns 0 when the table doesn't exist yet or the season has no rows.
    """
    settings = settings or get_settings()
    schema = "raw" if settings.warehouse == "duckdb" else settings.pg_schema
    try:
        df = read_query(
            f'select max(round) as max_round from {schema}."{table}" where season = {int(season)}',
            settings,
        )
    except Exception as exc:  # table/schema not created yet -> nothing loaded
        log.info("warehouse.watermark_absent", table=table, season=season, error=str(exc))
        return 0
    if df.empty or pd.isna(df["max_round"].iloc[0]):
        return 0
    return int(df["max_round"].iloc[0])


def replace_table(
    df: pd.DataFrame, schema: str, table: str, settings: Settings | None = None
) -> int:
    """Fully replace ``schema.table`` with ``df`` (used for non-partitioned marts).

    Returns the number of rows written.
    """
    settings = settings or get_settings()
    if settings.warehouse == "duckdb":
        settings.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect(str(settings.duckdb_path))
        try:
            con.register("incoming", df)
            con.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            con.execute(f'CREATE OR REPLACE TABLE "{schema}"."{table}" AS SELECT * FROM incoming')
        finally:
            con.unregister("incoming")
            con.close()
    else:
        engine = create_engine(settings.pg_dsn)
        try:
            with engine.begin() as conn:
                conn.exec_driver_sql(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
                df.to_sql(table, conn, schema=schema, if_exists="replace", index=False)
        finally:
            engine.dispose()
    log.info(
        "warehouse.replace_table",
        target=settings.warehouse,
        table=f"{schema}.{table}",
        rows=len(df),
    )
    return len(df)


def replace_table_partition(
    df: pd.DataFrame,
    schema: str,
    table: str,
    partition: dict[str, object],
    settings: Settings | None = None,
) -> int:
    """Atomically replace one partition of an analytics table with ``df``.

    This is the mart equivalent of ``load_dataframe(..., replace_rounds=True)``:
    rows outside the exact partition predicate are preserved. The delete still
    runs for an empty frame, which makes late source removals idempotent. Column
    and table names are internal constants; partition values remain bound
    parameters for both DuckDB and Postgres.
    """
    if not partition:
        raise ValueError("partition must contain at least one column")
    missing = set(partition) - set(df.columns)
    if missing:
        raise ValueError(f"incoming frame is missing partition columns: {sorted(missing)}")
    for column, value in partition.items():
        if not df.empty and not bool(df[column].eq(value).fillna(False).all()):
            raise ValueError(f"incoming frame contains rows outside partition {column}={value!r}")
    settings = settings or get_settings()

    if settings.warehouse == "duckdb":
        settings.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect(str(settings.duckdb_path))
        try:
            con.register("incoming", df)
            con.execute("BEGIN TRANSACTION")
            con.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            con.execute(
                f'CREATE TABLE IF NOT EXISTS "{schema}"."{table}" '
                "AS SELECT * FROM incoming WHERE 1 = 0"
            )
            _add_missing_frame_columns(con, schema, table, df)
            predicate = " AND ".join(f'"{column}" = ?' for column in partition)
            con.execute(
                f'DELETE FROM "{schema}"."{table}" WHERE {predicate}',
                list(partition.values()),
            )
            if not df.empty:
                con.execute(f'INSERT INTO "{schema}"."{table}" BY NAME SELECT * FROM incoming')
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        finally:
            con.unregister("incoming")
            con.close()
    else:
        engine = create_engine(settings.pg_dsn)
        try:
            with engine.begin() as conn:
                conn.exec_driver_sql(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
                df.head(0).to_sql(table, conn, schema=schema, if_exists="append", index=False)
                for column in df.columns:
                    sql_type = _portable_sql_type(df[column])
                    conn.exec_driver_sql(
                        f'ALTER TABLE "{schema}"."{table}" ADD COLUMN IF NOT EXISTS '
                        f'"{column}" {sql_type}'
                    )
                predicate = " AND ".join(
                    f'"{column}" = :partition_{index}' for index, column in enumerate(partition)
                )
                values = {
                    f"partition_{index}": value for index, value in enumerate(partition.values())
                }
                conn.execute(text(f'DELETE FROM "{schema}"."{table}" WHERE {predicate}'), values)
                if not df.empty:
                    df.to_sql(table, conn, schema=schema, if_exists="append", index=False)
        finally:
            engine.dispose()

    log.info(
        "warehouse.replace_table_partition",
        target=settings.warehouse,
        table=f"{schema}.{table}",
        partition=partition,
        rows=len(df),
    )
    return len(df)


def replace_mart_bundle(
    frames: Mapping[str, pd.DataFrame],
    settings: Settings,
    partition: dict[str, object] | None = None,
) -> None:
    """Commit dependent marts and their processing receipts in one transaction."""
    for table, frame in frames.items():
        if not table.isidentifier():
            raise ValueError(f"Invalid internal mart name: {table}")
        for key, value in (partition or {}).items():
            if key not in frame or (
                not frame.empty and not frame[key].eq(value).fillna(False).all()
            ):
                raise ValueError(f"Invalid {table} partition: {key}")
    if settings.warehouse == "duckdb":
        with duckdb.connect(str(settings.duckdb_path)) as connection:
            connection.execute("begin transaction")
            try:
                connection.execute("create schema if not exists marts")
                for table, frame in frames.items():
                    connection.register("bundle_frame", frame)
                    if partition is None:
                        connection.execute(
                            f'create or replace table marts."{table}" as select * from bundle_frame'
                        )
                    else:
                        connection.execute(
                            f'create table if not exists marts."{table}" as select * from bundle_frame where false'
                        )
                        predicate = " and ".join(f'"{key}" = ?' for key in partition)
                        connection.execute(
                            f'delete from marts."{table}" where {predicate}',
                            list(partition.values()),
                        )
                        connection.execute(
                            f'insert into marts."{table}" by name select * from bundle_frame'
                        )
                    connection.unregister("bundle_frame")
                connection.execute("commit")
            except Exception:
                connection.execute("rollback")
                raise
    else:
        engine = create_engine(settings.pg_dsn)
        try:
            with engine.begin() as connection:
                connection.exec_driver_sql("create schema if not exists marts")
                for table, frame in frames.items():
                    if partition is None:
                        frame.to_sql(
                            table, connection, schema="marts", if_exists="replace", index=False
                        )
                    else:
                        frame.head(0).to_sql(
                            table, connection, schema="marts", if_exists="append", index=False
                        )
                        predicate = " and ".join(f'"{key}" = :{key}' for key in partition)
                        connection.execute(
                            text(f'delete from marts."{table}" where {predicate}'), partition
                        )
                        frame.to_sql(
                            table, connection, schema="marts", if_exists="append", index=False
                        )
        finally:
            engine.dispose()
