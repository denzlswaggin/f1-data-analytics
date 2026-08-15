"""Load DataFrames into the raw schema of the warehouse (DuckDB or Postgres).

Loading is idempotent per season: the season's rows are deleted and re-inserted,
so re-running a backfill never duplicates data. The target is chosen by
``settings.warehouse`` so the same ingestion code serves dev (DuckDB) and prod
(Postgres).
"""

from __future__ import annotations

import duckdb
import pandas as pd
from sqlalchemy import create_engine, text

from ingestion.config import Settings, get_settings
from ingestion.logging import get_logger

log = get_logger(__name__)


def load_dataframe(
    df: pd.DataFrame, table: str, season: int, settings: Settings | None = None
) -> int:
    """Load ``df`` into ``raw.<table>`` for the given season. Returns row count."""
    settings = settings or get_settings()
    if df.empty:
        log.warning("warehouse.skip_empty", table=table, season=season)
        return 0

    if settings.warehouse == "duckdb":
        _load_duckdb(df, table, season, settings)
    else:
        _load_postgres(df, table, season, settings)

    log.info(
        "warehouse.load",
        target=settings.warehouse,
        table=table,
        season=season,
        rows=len(df),
    )
    return len(df)


def _load_duckdb(df: pd.DataFrame, table: str, season: int, settings: Settings) -> None:
    settings.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(settings.duckdb_path))
    try:
        con.register("incoming", df)
        con.execute("CREATE SCHEMA IF NOT EXISTS raw")
        # Create the table from the incoming shape if it doesn't exist yet.
        con.execute(
            f'CREATE TABLE IF NOT EXISTS raw."{table}" AS SELECT * FROM incoming WHERE 1 = 0'
        )
        con.execute(f'DELETE FROM raw."{table}" WHERE season = ?', [season])
        con.execute(f'INSERT INTO raw."{table}" SELECT * FROM incoming')
    finally:
        con.unregister("incoming")
        con.close()


def _load_postgres(df: pd.DataFrame, table: str, season: int, settings: Settings) -> None:
    engine = create_engine(settings.pg_dsn)
    schema = settings.pg_schema
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            # head(0) append creates the table if missing, else no-op.
            df.head(0).to_sql(table, conn, schema=schema, if_exists="append", index=False)
            conn.execute(
                text(f'DELETE FROM "{schema}"."{table}" WHERE season = :season'),
                {"season": season},
            )
            df.to_sql(table, conn, schema=schema, if_exists="append", index=False)
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
