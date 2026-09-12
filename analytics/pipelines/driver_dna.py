"""Warehouse IO boundary for Driver DNA and driver-track marts."""

from __future__ import annotations

import pandas as pd
from ingestion.config import Settings, get_settings
from ingestion.loaders.warehouse import read_query, replace_table, replace_table_partition
from ingestion.logging import get_logger

from analytics.driver_dna import (
    EVIDENCE_COLUMNS,
    DriverDNAResult,
    analyse_driver_dna,
    build_profile_windows,
    robust_standardize,
    validate_driver_dna,
)
from analytics.driver_dna_validation import (
    DriverDNAValidationResult,
    validate_driver_dna_stability,
)
from analytics.driver_track import DriverTrackResult, analyse_driver_track, validate_driver_track

log = get_logger(__name__)


def _where(
    from_season: int | None,
    to_season: int | None,
    rnd: int | None,
    *,
    alias: str = "",
) -> str:
    prefix = f"{alias}." if alias else ""
    predicates = [f"{prefix}session = 'R'"]
    if from_season is not None:
        predicates.append(f"{prefix}season >= {int(from_season)}")
    if to_season is not None:
        predicates.append(f"{prefix}season <= {int(to_season)}")
    if rnd is not None:
        if from_season is None or to_season != from_season:
            raise ValueError("round scope requires one exact season")
        predicates.append(f"{prefix}round = {int(rnd)}")
    return " and ".join(predicates)


def _sources(
    settings: Settings,
    *,
    from_season: int | None,
    to_season: int | None,
    rnd: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    where = _where(from_season, to_season, rnd, alias="laps")
    telemetry_where = (
        _where(from_season, to_season, rnd)
        .replace("session = 'R' and ", "")
        .replace("session = 'R'", "1 = 1")
    )
    telemetry = read_query(
        f"""
        select season, round, driver_code, lap_number, distance_m, speed_kph,
               throttle, brake, gear, x, y
        from marts.mart_lap_telemetry
        where {telemetry_where}
        order by season, round, driver_code, lap_number, distance_m
        """,
        settings,
    )
    laps = read_query(
        f"""
        select laps.season, laps.round, laps.driver_code, laps.lap_number,
               races.race_name, coalesce(codes.driver_name, laps.driver_code) as driver_name,
               laps.team, laps.compound, laps.tyre_life, laps.track_status,
               laps.lap_time_sec
        from staging.stg_laps as laps
        left join staging.stg_races as races
          on races.season = laps.season and races.round = laps.round
        left join staging.stg_driver_codes as codes
          on codes.season = laps.season and codes.driver_code = laps.driver_code
        where {where}
        """,
        settings,
    )
    return telemetry, laps


def _replace(result: DriverDNAResult, settings: Settings) -> None:
    replace_table(result.evidence, schema="marts", table="driver_dna_evidence", settings=settings)
    replace_table(result.profile, schema="marts", table="driver_dna_profile", settings=settings)
    replace_table(
        result.microsectors,
        schema="marts",
        table="driver_dna_microsectors",
        settings=settings,
    )


def build_driver_dna(
    from_season: int = 2024,
    to_season: int | None = None,
    settings: Settings | None = None,
    *,
    n_boot: int = 1000,
    seed: int = 0,
) -> DriverDNAResult:
    """Build all Driver DNA marts for a bounded multi-season scope."""
    settings = settings or get_settings()
    telemetry, laps = _sources(settings, from_season=from_season, to_season=to_season, rnd=None)
    result = analyse_driver_dna(telemetry, laps, n_boot=n_boot, seed=seed)
    validate_driver_dna(result)
    _replace(result, settings)
    log.info(
        "driver_dna.materialised",
        evidence_rows=len(result.evidence),
        eligible_rows=int(result.evidence["eligible"].sum()) if not result.evidence.empty else 0,
        profiles=len(result.profile),
        microsectors=len(result.microsectors),
        from_season=from_season,
        to_season=to_season,
    )
    return result


def build_driver_dna_validation(
    from_season: int = 2024,
    to_season: int | None = None,
    settings: Settings | None = None,
    *,
    n_permutations: int = 200,
    seed: int = 0,
) -> DriverDNAValidationResult:
    """Evaluate the persisted Driver DNA evidence against its source laps."""
    settings = settings or get_settings()
    telemetry, laps = _sources(settings, from_season=from_season, to_season=to_season, rnd=None)
    try:
        evidence = read_query(
            "select * from marts.driver_dna_evidence "
            f"where season >= {int(from_season)}"
            + (f" and season <= {int(to_season)}" if to_season is not None else ""),
            settings,
        )
    except Exception:
        evidence = analyse_driver_dna(telemetry, laps, n_boot=0, seed=seed).evidence
    return validate_driver_dna_stability(
        evidence,
        telemetry,
        laps,
        n_permutations=n_permutations,
        seed=seed,
    )


def build_driver_track_insights(settings: Settings | None = None) -> DriverTrackResult:
    """Materialise circuit archetypes, driver-track fit and DNA stability marts."""
    settings = settings or get_settings()
    evidence = read_query("select * from marts.driver_dna_evidence", settings)
    microsectors = read_query("select * from marts.driver_dna_microsectors", settings)
    result = analyse_driver_track(evidence, microsectors)
    validate_driver_track(result)
    replace_table(
        result.archetypes,
        schema="marts",
        table="driver_track_archetypes",
        settings=settings,
    )
    replace_table(
        result.driver_fit,
        schema="marts",
        table="driver_track_fit",
        settings=settings,
    )
    replace_table(
        result.dna_stability,
        schema="marts",
        table="driver_dna_stability",
        settings=settings,
    )
    log.info(
        "driver_track.materialised",
        races=len(result.archetypes),
        fit_rows=len(result.driver_fit),
        stability_rows=len(result.dna_stability),
    )
    return result


def _read_existing_evidence(settings: Settings) -> pd.DataFrame:
    try:
        evidence = read_query("select * from marts.driver_dna_evidence", settings)
        for column in EVIDENCE_COLUMNS:
            if column not in evidence:
                evidence[column] = pd.NA
        return evidence[EVIDENCE_COLUMNS]
    except Exception:
        return pd.DataFrame(columns=EVIDENCE_COLUMNS)


def build_driver_dna_incremental(
    season: int,
    rnd: int,
    settings: Settings | None = None,
    *,
    n_boot: int = 1000,
    seed: int = 0,
) -> DriverDNAResult:
    """Recompute one race and refresh global scales without discarding other races."""
    settings = settings or get_settings()
    telemetry, laps = _sources(settings, from_season=season, to_season=season, rnd=rnd)
    race_result = analyse_driver_dna(telemetry, laps, n_boot=0, seed=seed)
    existing = _read_existing_evidence(settings)
    outside = existing[~((existing["season"] == season) & (existing["round"] == rnd))].copy()
    combined = pd.concat([outside, race_result.evidence], ignore_index=True)
    combined = robust_standardize(combined)[EVIDENCE_COLUMNS]
    profiles = build_profile_windows(combined, n_boot=n_boot, seed=seed)
    validate_driver_dna(DriverDNAResult(combined, profiles, race_result.microsectors))
    replace_table(combined, schema="marts", table="driver_dna_evidence", settings=settings)
    replace_table_partition(
        race_result.microsectors,
        schema="marts",
        table="driver_dna_microsectors",
        partition={"season": season, "round": rnd},
        settings=settings,
    )
    replace_table(profiles, schema="marts", table="driver_dna_profile", settings=settings)
    log.info(
        "driver_dna.materialised_partition",
        season=season,
        round=rnd,
        evidence_rows=len(race_result.evidence),
        profiles=len(profiles),
        microsectors=len(race_result.microsectors),
    )
    return DriverDNAResult(race_result.evidence, profiles, race_result.microsectors)
