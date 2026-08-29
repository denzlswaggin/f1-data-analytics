"""Restore a warehouse partition from the durable Parquet lake."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from ingestion.config import Settings, get_settings
from ingestion.loaders.warehouse import load_dataframe

_RESOURCE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def _local_locations(
    resource: str, season: int, round_: int | None, settings: Settings
) -> list[str]:
    base = settings.lake_dir / resource / f"season={season}"
    if round_ is None:
        candidates = [base / "data.parquet"]
    else:
        round_dir = base / f"round={round_}"
        candidates = [round_dir / "data.parquet", *sorted(round_dir.glob("session=*/data.parquet"))]
    return [str(path) for path in candidates if Path(path).is_file()]


def _remote_locations(
    resource: str, season: int, round_: int | None, settings: Settings
) -> list[str]:
    import fsspec

    filesystem, root = fsspec.core.url_to_fs(settings.lake_uri.rstrip("/"))
    base = f"{root.rstrip('/')}/{resource}/season={season}"
    patterns = (
        [f"{base}/data.parquet"]
        if round_ is None
        else [
            f"{base}/round={round_}/data.parquet",
            f"{base}/round={round_}/session=*/data.parquet",
        ]
    )
    paths = sorted({path for pattern in patterns for path in filesystem.glob(pattern)})
    return [filesystem.unstrip_protocol(path) for path in paths]


def restore_lake_partition(
    resource: str,
    season: int,
    *,
    round_: int | None = None,
    settings: Settings | None = None,
) -> int:
    """Reload one season- or round-grain partition without calling an external API.

    For round/session lakes all sessions under the round are restored together.
    Warehouse round replacement deletes the whole round, so loading the complete
    set prevents a race-session recovery from accidentally removing qualifying.
    """
    if not _RESOURCE_NAME.fullmatch(resource):
        raise ValueError(f"invalid resource name: {resource!r}")
    settings = settings or get_settings()
    locations = (
        _remote_locations(resource, season, round_, settings)
        if settings.lake_is_remote
        else _local_locations(resource, season, round_, settings)
    )
    if not locations:
        grain = f"season={season}" if round_ is None else f"season={season}/round={round_}"
        raise FileNotFoundError(f"no lake partition found for {resource}/{grain}")

    frame = pd.concat([pd.read_parquet(location) for location in locations], ignore_index=True)
    if frame.empty:
        raise ValueError("refusing to restore an empty lake partition")
    if "season" not in frame or set(frame["season"].astype(int)) != {season}:
        raise ValueError("lake partition contents do not match the requested season")
    if round_ is not None and ("round" not in frame or set(frame["round"].astype(int)) != {round_}):
        raise ValueError("lake partition contents do not match the requested round")

    return load_dataframe(
        frame,
        resource,
        season,
        settings,
        replace_rounds=round_ is not None,
    )
