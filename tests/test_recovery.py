"""Tests for targeted lake-to-warehouse recovery."""

from pathlib import Path

import duckdb
import pandas as pd
import pytest
from ingestion.config import Settings
from ingestion.loaders.lake import write_parquet
from ingestion.loaders.warehouse import load_dataframe
from ingestion.recovery import restore_lake_partition


def test_restore_round_loads_all_session_partitions(tmp_path: Path) -> None:
    settings = Settings(
        duckdb_path=tmp_path / "warehouse.duckdb",
        lake_dir=tmp_path / "lake",
    )
    lake_frame = pd.DataFrame(
        {
            "season": [2024, 2024],
            "round": [1, 1],
            "session": ["Q", "R"],
            "value": [10, 20],
        }
    )
    write_parquet(
        lake_frame,
        "laps",
        2024,
        settings,
        partition_by=("round", "session"),
    )
    load_dataframe(
        lake_frame.assign(value=[-1, -1]),
        "laps",
        2024,
        settings,
        replace_rounds=True,
    )

    restored = restore_lake_partition("laps", 2024, round_=1, settings=settings)

    with duckdb.connect(str(settings.duckdb_path), read_only=True) as connection:
        rows = connection.execute("select session, value from raw.laps order by session").fetchall()
    assert restored == 2
    assert rows == [("Q", 10), ("R", 20)]


def test_restore_season_partition(tmp_path: Path) -> None:
    settings = Settings(
        duckdb_path=tmp_path / "warehouse.duckdb",
        lake_dir=tmp_path / "lake",
    )
    frame = pd.DataFrame({"season": [2024], "round": [1], "name": ["Bahrain"]})
    write_parquet(frame, "races", 2024, settings)

    assert restore_lake_partition("races", 2024, settings=settings) == 1


def test_restore_rejects_missing_or_invalid_partition(tmp_path: Path) -> None:
    settings = Settings(
        duckdb_path=tmp_path / "warehouse.duckdb",
        lake_dir=tmp_path / "lake",
    )

    with pytest.raises(ValueError, match="invalid resource"):
        restore_lake_partition("laps; drop table", 2024, settings=settings)
    with pytest.raises(FileNotFoundError, match="no lake partition"):
        restore_lake_partition("laps", 2024, round_=1, settings=settings)
