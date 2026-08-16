"""Idempotency tests for the per-season warehouse loader (DuckDB, temp file).

These lock in the delete-then-insert-per-season contract that every per-round
ingest relies on: re-loading a season replaces only that season's rows.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from ingestion.config import Settings
from ingestion.loaders.warehouse import load_dataframe, read_query


def _settings(tmp_path: Path) -> Settings:
    return Settings(warehouse="duckdb", duckdb_path=tmp_path / "f1.duckdb")


def _frame(season: int, rows: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "season": [season] * rows,
            "round": list(range(1, rows + 1)),
            "val": list(range(rows)),
        }
    )


def test_reload_same_season_is_idempotent(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    load_dataframe(_frame(2024, 3), "pitstops", 2024, settings)
    load_dataframe(_frame(2024, 3), "pitstops", 2024, settings)  # re-run
    out = read_query("select count(*) as n from raw.pitstops", settings)
    assert int(out["n"][0]) == 3  # not doubled


def test_load_only_replaces_its_own_season(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    load_dataframe(_frame(2023, 2), "pitstops", 2023, settings)
    load_dataframe(_frame(2024, 3), "pitstops", 2024, settings)
    # Reloading 2024 (now 5 rows) must leave 2023 untouched.
    load_dataframe(_frame(2024, 5), "pitstops", 2024, settings)
    out = read_query(
        "select season, count(*) as n from raw.pitstops group by season order by season",
        settings,
    )
    counts = dict(zip(out["season"].tolist(), out["n"].tolist(), strict=True))
    assert counts == {2023: 2, 2024: 5}
