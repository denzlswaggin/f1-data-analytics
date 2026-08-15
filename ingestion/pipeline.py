"""Extract-Load pipeline: API -> flatten -> Parquet lake -> warehouse."""

from __future__ import annotations

from typing import Any

import pandas as pd

from ingestion.clients.jolpica import JolpicaClient
from ingestion.config import Settings, get_settings
from ingestion.loaders.lake import write_parquet
from ingestion.loaders.warehouse import load_dataframe
from ingestion.logging import get_logger
from ingestion.resources import DEFAULT_RESOURCES, RESOURCES, Resource

log = get_logger(__name__)


def extract_resource(resource: Resource, season: int, client: JolpicaClient) -> pd.DataFrame:
    """Fetch and flatten one resource for one season into a DataFrame."""
    path = resource.path_template.format(season=season)
    rows: list[dict[str, Any]] = []
    for record in client.paginate(path, resource.table_key, resource.list_key):
        rows.extend(resource.flatten(record, season))
    return pd.DataFrame(rows)


def ingest_resource(
    resource_name: str,
    season: int,
    client: JolpicaClient | None = None,
    settings: Settings | None = None,
) -> int:
    """Run the full EL path for one resource/season. Returns rows loaded."""
    settings = settings or get_settings()
    client = client or JolpicaClient(settings)
    resource = RESOURCES[resource_name]

    df = extract_resource(resource, season, client)
    if df.empty:
        log.warning("pipeline.empty", resource=resource_name, season=season)
        return 0

    write_parquet(df, resource.name, season, settings)
    return load_dataframe(df, resource.name, season, settings)


def backfill(
    seasons: list[int],
    resources: tuple[str, ...] = DEFAULT_RESOURCES,
    settings: Settings | None = None,
) -> dict[tuple[str, int], int]:
    """Backfill the given resources across the given seasons.

    Returns a ``{(resource, season): rows_loaded}`` summary.
    """
    settings = settings or get_settings()
    client = JolpicaClient(settings)
    summary: dict[tuple[str, int], int] = {}
    for season in seasons:
        for resource_name in resources:
            rows = ingest_resource(resource_name, season, client, settings)
            summary[(resource_name, season)] = rows
    return summary


def ingest_laps(
    season: int,
    rounds: list[int],
    session: str = "R",
    settings: Settings | None = None,
) -> int:
    """Ingest FastF1 per-lap data for a set of rounds in one season.

    All requested rounds are collected into a single season DataFrame and loaded
    idempotently per season (re-running replaces the season's laps). Returns rows
    loaded. FastF1 is a heavy optional dependency, imported here.
    """
    settings = settings or get_settings()
    from ingestion.clients.fastf1_client import FastF1Client

    client = FastF1Client(settings)
    frames = []
    for rnd in rounds:
        df = client.load_session_laps(season, rnd, session)
        if not df.empty:
            frames.append(df)

    if not frames:
        log.warning("pipeline.laps_empty", season=season, rounds=rounds)
        return 0

    laps = pd.concat(frames, ignore_index=True)
    write_parquet(laps, "laps", season, settings)
    return load_dataframe(laps, "laps", season, settings)
