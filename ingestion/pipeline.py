"""Extract-Load pipeline: API -> flatten -> Parquet lake -> warehouse."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pandas as pd

from ingestion.clients.jolpica import JolpicaClient
from ingestion.config import Settings, get_settings
from ingestion.loaders.lake import write_parquet
from ingestion.loaders.warehouse import load_dataframe, read_query
from ingestion.logging import get_logger
from ingestion.resources import (
    DEFAULT_RESOURCES,
    RESOURCES,
    Resource,
    _flatten_ergast_laps,
    _flatten_pitstops,
)

log = get_logger(__name__)

# A per-round flattener takes one Race envelope + the season and yields rows.
PerRoundFlattener = Any


def season_rounds(
    season: int, completed_only: bool = False, settings: Settings | None = None
) -> list[int]:
    """Return the round numbers of a season, read from ``raw.races``.

    ``completed_only`` keeps rounds whose race date is on/before today — the
    basis for a "season so far" backfill. Returns ``[]`` (with a warning) if the
    races table hasn't been ingested yet, so callers can fall back gracefully.
    """
    settings = settings or get_settings()
    try:
        df = read_query(f"select round, date from raw.races where season = {int(season)}", settings)
    except Exception as exc:  # races not ingested yet is non-fatal
        log.warning("pipeline.season_rounds_unavailable", season=season, error=str(exc))
        return []
    if df.empty:
        return []
    if completed_only:
        today = dt.date.today().isoformat()
        df = df[df["date"].astype("string") <= today]
    return sorted(int(r) for r in df["round"].tolist())


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


def ingest_weather(
    season: int, rounds: list[int], session: str = "R", settings: Settings | None = None
) -> int:
    """Ingest FastF1 per-minute weather for a set of rounds in one season."""
    settings = settings or get_settings()
    from ingestion.clients.fastf1_client import FastF1Client

    client = FastF1Client(settings)
    frames = []
    for rnd in rounds:
        df = client.load_session_weather(season, rnd, session)
        if not df.empty:
            frames.append(df)

    if not frames:
        log.warning("pipeline.weather_empty", season=season, rounds=rounds)
        return 0

    weather = pd.concat(frames, ignore_index=True)
    write_parquet(weather, "weather", season, settings)
    return load_dataframe(weather, "weather", season, settings)


def ingest_telemetry(
    season: int, rounds: list[int], session: str = "R", settings: Settings | None = None
) -> int:
    """Ingest FastF1 distance-resampled telemetry for a set of rounds (heavy)."""
    settings = settings or get_settings()
    from ingestion.clients.fastf1_client import FastF1Client

    client = FastF1Client(settings)
    frames = []
    for rnd in rounds:
        df = client.load_session_telemetry(season, rnd, session)
        if not df.empty:
            frames.append(df)

    if not frames:
        log.warning("pipeline.telemetry_empty", season=season, rounds=rounds)
        return 0

    telemetry = pd.concat(frames, ignore_index=True)
    write_parquet(telemetry, "telemetry", season, settings)
    return load_dataframe(telemetry, "telemetry", season, settings)


def ingest_positions(
    season: int, rounds: list[int], session: str = "R", settings: Settings | None = None
) -> int:
    """Ingest FastF1 time-stamped car positions for a set of rounds (heavy).

    Feeds the race-replay map: one row per driver per position sample, on the
    shared session clock. All rounds are concatenated into one season frame and
    loaded once (the loader's delete key is ``season`` only).
    """
    settings = settings or get_settings()
    from ingestion.clients.fastf1_client import FastF1Client

    client = FastF1Client(settings)
    frames = []
    for rnd in rounds:
        df = client.load_session_position(season, rnd, session)
        if not df.empty:
            frames.append(df)

    if not frames:
        log.warning("pipeline.positions_empty", season=season, rounds=rounds)
        return 0

    positions = pd.concat(frames, ignore_index=True)
    write_parquet(positions, "positions", season, settings)
    return load_dataframe(positions, "positions", season, settings)


def ingest_race_control(
    season: int, rounds: list[int], session: str = "R", settings: Settings | None = None
) -> int:
    """Ingest FastF1 race-control messages for a set of rounds in one season.

    Reads from the FastF1 cache for the session-time reference, so it's light once
    telemetry is cached. All rounds are concatenated into one season frame and
    loaded once (the loader's delete key is ``season`` only).
    """
    settings = settings or get_settings()
    from ingestion.clients.fastf1_client import FastF1Client

    client = FastF1Client(settings)
    frames = []
    for rnd in rounds:
        df = client.load_session_race_control(season, rnd, session)
        if not df.empty:
            frames.append(df)

    if not frames:
        log.warning("pipeline.race_control_empty", season=season, rounds=rounds)
        return 0

    messages = pd.concat(frames, ignore_index=True)
    write_parquet(messages, "race_control", season, settings)
    return load_dataframe(messages, "race_control", season, settings)


def _extract_per_round(
    client: JolpicaClient,
    season: int,
    rounds: list[int],
    path_suffix: str,
    flatten: PerRoundFlattener,
) -> pd.DataFrame:
    """Page a per-round Jolpica endpoint over several rounds into one frame.

    All rounds are collected into a single season DataFrame so the per-season
    idempotent loader replaces the whole season at once (loading round-by-round
    would delete earlier rounds — the loader's delete key is ``season`` only).
    """
    rows: list[dict[str, Any]] = []
    for rnd in rounds:
        path = f"{season}/{rnd}/{path_suffix}"
        for record in client.paginate(path, "RaceTable", "Races"):
            rows.extend(flatten(record, season))
    return pd.DataFrame(rows)


def ingest_pitstops(season: int, rounds: list[int], settings: Settings | None = None) -> int:
    """Ingest Ergast pit-stop timing for a set of rounds in one season."""
    settings = settings or get_settings()
    client = JolpicaClient(settings)
    df = _extract_per_round(client, season, rounds, "pitstops", _flatten_pitstops)
    if df.empty:
        log.warning("pipeline.pitstops_empty", season=season, rounds=rounds)
        return 0
    write_parquet(df, "pitstops", season, settings)
    return load_dataframe(df, "pitstops", season, settings)


def ingest_ergast_laps(season: int, rounds: list[int], settings: Settings | None = None) -> int:
    """Ingest Ergast per-lap position/time for a set of rounds in one season."""
    settings = settings or get_settings()
    client = JolpicaClient(settings)
    df = _extract_per_round(client, season, rounds, "laps", _flatten_ergast_laps)
    if df.empty:
        log.warning("pipeline.ergast_laps_empty", season=season, rounds=rounds)
        return 0
    write_parquet(df, "ergast_laps", season, settings)
    return load_dataframe(df, "ergast_laps", season, settings)
