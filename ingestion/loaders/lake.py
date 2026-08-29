"""Write flattened records to a partitioned Parquet lake.

Season-grain resources keep one file per resource/season::

    {lake_dir}/{resource}/season={season}/data.parquet

Per-round resources can additionally partition by round and session::

    {lake_dir}/{resource}/season={season}/round={round}/session={session}/data.parquet

The lake is storage-agnostic: with ``settings.lake_uri`` set to an object-store
base (``s3://…``, ``gs://…``) the same partitions are written there via fsspec,
so the identical ingestion code serves a local disk lake and a cloud one.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Literal, overload
from uuid import uuid4

import pandas as pd

from ingestion.config import Settings, get_settings
from ingestion.logging import get_logger

log = get_logger(__name__)


PartitionColumn = Literal["round", "session"]


def _partition_key(
    resource: str,
    season: int,
    *,
    round_: int | None = None,
    session: str | None = None,
) -> str:
    """Relative object key of a lake partition (POSIX-style, for URIs)."""
    parts = [resource, f"season={season}"]
    if round_ is not None:
        parts.append(f"round={round_}")
    if session is not None:
        parts.append(f"session={session}")
    return "/".join([*parts, "data.parquet"])


def partition_path(
    resource: str,
    season: int,
    settings: Settings | None = None,
    *,
    round_: int | None = None,
    session: str | None = None,
) -> Path:
    """Return the local path for a season, round, or round/session partition."""
    settings = settings or get_settings()
    return settings.lake_dir / _partition_key(resource, season, round_=round_, session=session)


def _atomic_write_local(df: pd.DataFrame, path: Path) -> None:
    """Write via a sibling temporary file, then atomically replace ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        df.to_parquet(temporary, index=False, engine="pyarrow")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_remote(df: pd.DataFrame, target: str) -> None:
    """Stage a remote object before replacing its final key.

    Object-store moves are implemented by the configured fsspec backend. The old
    object therefore remains readable if serialisation or upload of the staged
    object fails; the final replace inherits that backend's rename semantics.
    """
    import fsspec

    filesystem, target_path = fsspec.core.url_to_fs(target)
    temporary_path = f"{target_path}.tmp-{uuid4().hex}"
    protocol = target.split("://", maxsplit=1)[0]
    temporary_uri = f"{protocol}://{temporary_path}"
    try:
        df.to_parquet(temporary_uri, index=False, engine="pyarrow")
        filesystem.mv(temporary_path, target_path)
    finally:
        if filesystem.exists(temporary_path):
            filesystem.rm(temporary_path)


def _partition_frames(
    df: pd.DataFrame, partition_by: tuple[PartitionColumn, ...]
) -> Iterator[tuple[pd.DataFrame, int | None, str | None]]:
    """Yield frames and canonical round/session values for requested partitions."""
    if not partition_by:
        yield df, None, None
        return

    if partition_by not in {("round",), ("round", "session")}:
        raise ValueError("partition_by must be (), ('round',), or ('round', 'session')")
    missing = set(partition_by) - set(df.columns)
    if missing:
        raise ValueError(f"partition columns missing from frame: {sorted(missing)}")
    if df.loc[:, list(partition_by)].isna().any(axis=None):
        raise ValueError("partition columns cannot contain null values")

    grouper: str | list[str] = (
        str(partition_by[0]) if len(partition_by) == 1 else [str(column) for column in partition_by]
    )
    for values, frame in df.groupby(grouper, sort=True, dropna=False):
        value_tuple = values if isinstance(values, tuple) else (values,)
        round_ = int(value_tuple[0])
        session = str(value_tuple[1]) if len(value_tuple) == 2 else None
        if session is not None and (not session or "/" in session or "\\" in session):
            raise ValueError(f"invalid session partition value: {session!r}")
        yield frame.reset_index(drop=True), round_, session


@overload
def write_parquet(
    df: pd.DataFrame,
    resource: str,
    season: int,
    settings: Settings | None = None,
    *,
    partition_by: tuple[()] = (),
) -> str: ...


@overload
def write_parquet(
    df: pd.DataFrame,
    resource: str,
    season: int,
    settings: Settings | None = None,
    *,
    partition_by: tuple[PartitionColumn, ...],
) -> list[str]: ...


def write_parquet(
    df: pd.DataFrame,
    resource: str,
    season: int,
    settings: Settings | None = None,
    *,
    partition_by: tuple[PartitionColumn, ...] = (),
) -> str | list[str]:
    """Atomically replace the selected Parquet lake partition(s).

    The default keeps the original season-only layout and return type. Passing
    ``partition_by=("round",)`` or ``("round", "session")`` writes one file per
    group and returns all target locations. Re-running one round replaces only
    that round, leaving the rest of the season intact.
    """
    settings = settings or get_settings()
    targets: list[str] = []
    for frame, round_, session in _partition_frames(df, partition_by):
        key = _partition_key(resource, season, round_=round_, session=session)
        if settings.lake_is_remote:
            target = f"{settings.lake_uri.rstrip('/')}/{key}"
            _atomic_write_remote(frame, target)
        else:
            path = settings.lake_dir / key
            _atomic_write_local(frame, path)
            target = str(path)
        targets.append(target)

    log.info(
        "lake.write",
        resource=resource,
        season=season,
        rows=len(df),
        partitions=len(targets),
        targets=targets,
        remote=settings.lake_is_remote,
    )
    return targets if partition_by else targets[0]
