"""Write flattened records to a partitioned Parquet lake.

Layout (one file per resource/season, overwritten idempotently)::

    {lake_dir}/{resource}/season={season}/data.parquet

The lake is storage-agnostic: with ``settings.lake_uri`` set to an object-store
base (``s3://…``, ``gs://…``) the same partitions are written there via fsspec,
so the identical ingestion code serves a local disk lake and a cloud one.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ingestion.config import Settings, get_settings
from ingestion.logging import get_logger

log = get_logger(__name__)


def _partition_key(resource: str, season: int) -> str:
    """Relative object key of a resource/season partition (POSIX-style, for URIs)."""
    return f"{resource}/season={season}/data.parquet"


def partition_path(resource: str, season: int, settings: Settings | None = None) -> Path:
    """Return the local Parquet file path for a resource/season partition."""
    settings = settings or get_settings()
    return settings.lake_dir / resource / f"season={season}" / "data.parquet"


def write_parquet(
    df: pd.DataFrame, resource: str, season: int, settings: Settings | None = None
) -> str:
    """Write ``df`` to its season partition, overwriting any prior file.

    Overwriting the whole partition file makes re-runs idempotent: the lake always
    reflects the latest fetch. Returns the target location (local path or URI).
    Writes to the object store when ``settings.lake_uri`` is set, else to disk.
    """
    settings = settings or get_settings()
    if settings.lake_is_remote:
        target = f"{settings.lake_uri.rstrip('/')}/{_partition_key(resource, season)}"
        # pyarrow dispatches to fsspec on the URI scheme (s3://, gs://, memory://…).
        df.to_parquet(target, index=False, engine="pyarrow")
    else:
        path = partition_path(resource, season, settings)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path, index=False, engine="pyarrow")
        target = str(path)
    log.info(
        "lake.write",
        resource=resource,
        season=season,
        rows=len(df),
        target=target,
        remote=settings.lake_is_remote,
    )
    return target
