"""Idempotency tests for the warehouse loader (DuckDB, temp file).

These lock in two contracts:
- the default delete-then-insert-per-season replace, and
- the round-aware ``replace_rounds=True`` path that lets an incremental run
  append new rounds without wiping the rounds already loaded (+ its watermark).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from ingestion.config import Settings
from ingestion.loaders.warehouse import latest_loaded_round, load_dataframe, read_query


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


def _round_frame(season: int, rounds: list[int]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "season": [season] * len(rounds),
            "round": rounds,
            "val": [r * 10 for r in rounds],
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


def test_replace_rounds_appends_new_rounds(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    load_dataframe(_round_frame(2024, [1, 2]), "laps", 2024, settings, replace_rounds=True)
    # An incremental run of a later round must append, not wipe rounds 1-2.
    load_dataframe(_round_frame(2024, [3]), "laps", 2024, settings, replace_rounds=True)
    out = read_query("select round from raw.laps order by round", settings)
    assert out["round"].tolist() == [1, 2, 3]


def test_replace_rounds_replaces_only_its_own_rounds(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    load_dataframe(_round_frame(2024, [1, 2, 3]), "laps", 2024, settings, replace_rounds=True)
    # Re-load round 2 only, with a new value: rounds 1 and 3 stay untouched.
    reload = pd.DataFrame({"season": [2024], "round": [2], "val": [999]})
    load_dataframe(reload, "laps", 2024, settings, replace_rounds=True)
    out = read_query("select round, val from raw.laps order by round", settings)
    assert out["round"].tolist() == [1, 2, 3]  # no duplicate round 2
    vals = dict(zip(out["round"].tolist(), out["val"].tolist(), strict=True))
    assert vals == {1: 10, 2: 999, 3: 30}


def test_latest_loaded_round_is_the_high_watermark(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    assert latest_loaded_round("laps", 2024, settings) == 0  # table absent yet
    load_dataframe(_round_frame(2024, [1, 2, 5]), "laps", 2024, settings, replace_rounds=True)
    assert latest_loaded_round("laps", 2024, settings) == 5
    assert latest_loaded_round("laps", 2023, settings) == 0  # season absent
