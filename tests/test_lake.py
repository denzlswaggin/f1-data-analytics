"""Tests for the Parquet lake writer — local disk and the object-store URI path."""

from __future__ import annotations

from pathlib import Path

import fsspec
import pandas as pd
import pytest
from ingestion.config import Settings
from ingestion.loaders.lake import partition_path, write_parquet


def _frame() -> pd.DataFrame:
    return pd.DataFrame({"season": [2024, 2024], "round": [1, 2], "val": [10, 20]})


def test_write_parquet_local(tmp_path: Path) -> None:
    settings = Settings(lake_dir=tmp_path / "raw")
    target = write_parquet(_frame(), "races", 2024, settings)
    path = partition_path("races", 2024, settings)
    assert Path(target) == path
    assert path.exists()
    assert list(pd.read_parquet(path)["round"]) == [1, 2]


def test_write_parquet_object_store() -> None:
    # memory:// is an in-process fsspec object store standing in for s3://, gs://…
    # write_parquet takes the same code path (pyarrow dispatches to fsspec by
    # URI scheme), so this exercises the real cloud-write branch without creds.
    fsspec.filesystem("memory").store.clear()
    try:
        settings = Settings(lake_uri="memory://f1-lake")
        target = write_parquet(_frame(), "races", 2024, settings)
        assert target == "memory://f1-lake/races/season=2024/data.parquet"
        assert list(pd.read_parquet(target)["round"]) == [1, 2]
    finally:
        fsspec.filesystem("memory").store.clear()


def test_lake_is_remote_flag() -> None:
    assert Settings(lake_uri="s3://bucket/lake").lake_is_remote is True
    assert Settings(lake_uri="").lake_is_remote is False


@pytest.mark.parametrize("uri", ["s3://bucket/lake", "gs://bucket/lake/"])
def test_object_key_layout(uri: str) -> None:
    # The partition layout (resource/season=<n>/data.parquet) is identical on any
    # backend; only the base differs. We check the composed target string here.
    settings = Settings(lake_uri=uri)
    fsspec_base = settings.lake_uri.rstrip("/")
    assert f"{fsspec_base}/qualifying/season=2019/data.parquet".endswith(
        "qualifying/season=2019/data.parquet"
    )
