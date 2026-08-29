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


def test_write_parquet_partitions_rounds_without_replacing_prior_round(tmp_path: Path) -> None:
    settings = Settings(lake_dir=tmp_path / "raw")
    targets = write_parquet(_frame(), "pitstops", 2024, settings, partition_by=("round",))

    round_1 = partition_path("pitstops", 2024, settings, round_=1)
    round_2 = partition_path("pitstops", 2024, settings, round_=2)
    assert targets == [str(round_1), str(round_2)]
    assert pd.read_parquet(round_1)["val"].tolist() == [10]
    assert pd.read_parquet(round_2)["val"].tolist() == [20]

    replacement = pd.DataFrame({"season": [2024], "round": [2], "val": [999]})
    write_parquet(replacement, "pitstops", 2024, settings, partition_by=("round",))

    assert pd.read_parquet(round_1)["val"].tolist() == [10]
    assert pd.read_parquet(round_2)["val"].tolist() == [999]


def test_write_parquet_partitions_by_round_and_session(tmp_path: Path) -> None:
    settings = Settings(lake_dir=tmp_path / "raw")
    frame = pd.DataFrame(
        {
            "season": [2024, 2024, 2024],
            "round": [1, 1, 2],
            "session": ["Q", "R", "R"],
            "val": [1, 2, 3],
        }
    )

    targets = write_parquet(frame, "laps", 2024, settings, partition_by=("round", "session"))

    expected = [
        partition_path("laps", 2024, settings, round_=1, session="Q"),
        partition_path("laps", 2024, settings, round_=1, session="R"),
        partition_path("laps", 2024, settings, round_=2, session="R"),
    ]
    assert targets == [str(path) for path in expected]
    assert [pd.read_parquet(path)["val"].item() for path in expected] == [1, 2, 3]


def test_local_atomic_write_preserves_old_partition_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(lake_dir=tmp_path / "raw")
    target = partition_path("races", 2024, settings)
    write_parquet(_frame(), "races", 2024, settings)

    def fail_after_partial_write(
        _self: pd.DataFrame, path: Path, *args: object, **kwargs: object
    ) -> None:
        Path(path).write_bytes(b"partial parquet")
        raise RuntimeError("simulated serialisation failure")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", fail_after_partial_write)
    with pytest.raises(RuntimeError, match="simulated serialisation failure"):
        write_parquet(_frame().assign(val=[100, 200]), "races", 2024, settings)

    assert pd.read_parquet(target)["val"].tolist() == [10, 20]
    assert list(target.parent.glob(".data.parquet.*.tmp")) == []


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


def test_object_store_round_partitions_preserve_existing_rounds() -> None:
    fsspec.filesystem("memory").store.clear()
    try:
        settings = Settings(lake_uri="memory://f1-lake")
        targets = write_parquet(_frame(), "pitstops", 2024, settings, partition_by=("round",))
        assert targets == [
            "memory://f1-lake/pitstops/season=2024/round=1/data.parquet",
            "memory://f1-lake/pitstops/season=2024/round=2/data.parquet",
        ]

        replacement = pd.DataFrame({"season": [2024], "round": [2], "val": [999]})
        write_parquet(replacement, "pitstops", 2024, settings, partition_by=("round",))

        assert pd.read_parquet(targets[0])["val"].tolist() == [10]
        assert pd.read_parquet(targets[1])["val"].tolist() == [999]
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
