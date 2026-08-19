"""Load DataFrames into the raw schema of the warehouse (DuckDB or Postgres).

Loading is idempotent: by default a whole season's rows are deleted and
re-inserted, so re-running a backfill never duplicates data. Per-round sources
can instead pass ``replace_rounds=True`` to delete-and-replace only the rounds
present in the frame, which lets an incremental run append *new* rounds without
wiping the rounds already loaded. The target is chosen by ``settings.warehouse``
so the same ingestion code serves dev (DuckDB) and prod (Postgres).
"""

from __future__ import annotations

import duckdb
import pandas as pd
from sqlalchemy import bindparam, create_engine, text

from ingestion.config import Settings, get_settings
from ingestion.logging import get_logger

log = get_logger(__name__)


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

    if settings.warehouse == "duckdb":
        _load_duckdb(df, table, season, settings, rounds if by_round else None)
    else:
        _load_postgres(df, table, season, settings, rounds if by_round else None)

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
) -> None:
    settings.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(settings.duckdb_path))
    try:
        con.register("incoming", df)
        con.execute("CREATE SCHEMA IF NOT EXISTS raw")
        # Create the table from the incoming shape if it doesn't exist yet.
        con.execute(
            f'CREATE TABLE IF NOT EXISTS raw."{table}" AS SELECT * FROM incoming WHERE 1 = 0'
        )
        if rounds is not None:
            placeholders = ", ".join("?" for _ in rounds)
            con.execute(
                f'DELETE FROM raw."{table}" WHERE season = ? AND round IN ({placeholders})',
                [season, *rounds],
            )
        else:
            con.execute(f'DELETE FROM raw."{table}" WHERE season = ?', [season])
        con.execute(f'INSERT INTO raw."{table}" SELECT * FROM incoming')
    finally:
        con.unregister("incoming")
        con.close()


def _load_postgres(
    df: pd.DataFrame,
    table: str,
    season: int,
    settings: Settings,
    rounds: list[int] | None,
) -> None:
    engine = create_engine(settings.pg_dsn)
    schema = settings.pg_schema
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            # head(0) append creates the table if missing, else no-op.
            df.head(0).to_sql(table, conn, schema=schema, if_exists="append", index=False)
            if rounds is not None:
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
