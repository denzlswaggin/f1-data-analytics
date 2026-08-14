"""Write flattened records to a partitioned Parquet lake.

Layout (one file per resource/season, overwritten idempotently)::

    {lake_dir}/{resource}/season={season}/data.parquet
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ingestion.config import Settings, get_settings
from ingestion.logging import get_logger

log = get_logger(__name__)


def partition_path(resource: str, season: int, settings: Settings | None = None) -> Path:
    """Return the Parquet file path for a resource/season partition."""
    settings = settings or get_settings()
    return settings.lake_dir / resource / f"season={season}" / "data.parquet"


def write_parquet(
    df: pd.DataFrame, resource: str, season: int, settings: Settings | None = None
) -> Path:
    """Write ``df`` to its season partition, overwriting any prior file.

    Overwriting the whole partition file makes re-runs idempotent: the lake
    always reflects the latest fetch for that resource/season.
    """
    path = partition_path(resource, season, settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False, engine="pyarrow")
    log.info("lake.write", resource=resource, season=season, rows=len(df), path=str(path))
    return path
