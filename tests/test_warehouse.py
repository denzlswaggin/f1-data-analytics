"""Tests for the idempotent, per-season warehouse loader.

``load_dataframe`` deletes a season's rows and re-inserts them, so re-running a
backfill must never duplicate data while leaving other seasons untouched. This is
core "don't corrupt the warehouse on re-run" logic; it was previously untested.
Only the DuckDB path runs here (``duckdb`` is a core dependency); the Postgres
branch has parallel semantics but needs a live server, so it stays a
manual/prod check.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from ingestion.config import Settings
from ingestion.loaders.warehouse import load_dataframe, read_query


def _results(season: int, driver_ids: list[str]) -> pd.DataFrame:
    """A minimal ``raw.results``-shaped frame carrying the ``season`` key."""
    return pd.DataFrame(
        [{"season": season, "driver_id": d, "points": float(i)} for i, d in enumerate(driver_ids)]
    )


def _count(settings: Settings, where: str = "") -> int:
    frame = read_query(f"select count(*) as n from raw.results {where}", settings)
    return int(frame["n"].iloc[0])


def test_load_dataframe_is_idempotent_per_season(tmp_path: Path) -> None:
    settings = Settings(warehouse="duckdb", duckdb_path=tmp_path / "f1.duckdb")
    df_2023 = _results(2023, ["ver", "per", "ham"])

    # First load establishes the season's rows.
    assert load_dataframe(df_2023, "results", 2023, settings) == 3
    assert _count(settings) == 3

    # Re-loading the same season is a no-op on row count (delete-then-insert).
    assert load_dataframe(df_2023, "results", 2023, settings) == 3
    assert _count(settings) == 3

    # A different season is additive and leaves the first season intact.
    df_2024 = _results(2024, ["ver", "nor", "lec", "pia"])
    assert load_dataframe(df_2024, "results", 2024, settings) == 4
    assert _count(settings) == 7
    assert _count(settings, "where season = 2023") == 3
    assert _count(settings, "where season = 2024") == 4


def test_load_dataframe_skips_empty(tmp_path: Path) -> None:
    settings = Settings(warehouse="duckdb", duckdb_path=tmp_path / "f1.duckdb")
    empty = pd.DataFrame(columns=["season", "driver_id", "points"])

    # An empty frame writes nothing and reports zero rows loaded.
    assert load_dataframe(empty, "results", 2023, settings) == 0
