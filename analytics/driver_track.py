"""Circuit archetypes and teammate-normalised driver-track fit summaries."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from analytics.driver_dna_validation import build_stability_windows

METHODOLOGY_VERSION = "driver-track-v1-descriptive"

ARCHETYPE_COLUMNS = [
    "season",
    "round",
    "race_name",
    "circuit_archetype",
    "average_speed_kph",
    "braking_density_pct",
    "full_throttle_pct",
    "low_speed_segment_pct",
    "segments",
    "confidence",
    "methodology_version",
]

FIT_COLUMNS = [
    "driver_code",
    "driver_name",
    "circuit_archetype",
    "n_races",
    "median_gain_sec",
    "mean_gain_sec",
    "gain_direction_agreement_pct",
    "confidence",
    "methodology_version",
]


@dataclass(frozen=True)
class DriverTrackResult:
    archetypes: pd.DataFrame
    driver_fit: pd.DataFrame
    dna_stability: pd.DataFrame


def classify_circuit_archetypes(microsectors: pd.DataFrame) -> pd.DataFrame:
    """Classify races from observed fast-lap speed, throttle and braking mix."""
    if microsectors.empty:
        return pd.DataFrame(columns=ARCHETYPE_COLUMNS)
    canonical = microsectors[
        microsectors["driver_code"].astype(str) < microsectors["teammate_code"].astype(str)
    ].copy()
    canonical["pair_speed"] = (canonical["driver_speed_kph"] + canonical["teammate_speed_kph"]) / 2
    canonical["pair_brake"] = (
        canonical["driver_brake_share"] + canonical["teammate_brake_share"]
    ) / 2
    canonical["pair_throttle"] = (canonical["driver_throttle"] + canonical["teammate_throttle"]) / 2
    grouped = (
        canonical.groupby(["season", "round", "race_name"], as_index=False)
        .agg(
            average_speed_kph=("pair_speed", "mean"),
            braking_density=("pair_brake", "mean"),
            full_throttle_share=("pair_throttle", lambda values: float((values >= 99).mean())),
            low_speed_share=("pair_speed", lambda values: float((values <= 160).mean())),
            segments=("segment_number", "count"),
        )
        .sort_values(["season", "round"])
    )
    speed_high = float(grouped["average_speed_kph"].quantile(0.67))
    brake_high = float(grouped["braking_density"].quantile(0.67))
    low_speed_high = float(grouped["low_speed_share"].quantile(0.67))
    conditions = [
        (grouped["average_speed_kph"] >= speed_high) & (grouped["braking_density"] < brake_high),
        grouped["braking_density"] >= brake_high,
        grouped["low_speed_share"] >= low_speed_high,
    ]
    grouped["circuit_archetype"] = np.select(
        conditions,
        ["High-speed flow", "Heavy braking", "Low-speed traction"],
        default="Balanced",
    )
    grouped["braking_density_pct"] = grouped.pop("braking_density") * 100
    grouped["full_throttle_pct"] = grouped.pop("full_throttle_share") * 100
    grouped["low_speed_segment_pct"] = grouped.pop("low_speed_share") * 100
    grouped["confidence"] = np.where(grouped["segments"] >= 100, "strong", "limited")
    grouped["methodology_version"] = METHODOLOGY_VERSION
    return grouped[ARCHETYPE_COLUMNS].reset_index(drop=True)


def build_driver_track_fit(microsectors: pd.DataFrame, archetypes: pd.DataFrame) -> pd.DataFrame:
    """Aggregate directed teammate-relative microsector gains by archetype."""
    if microsectors.empty or archetypes.empty:
        return pd.DataFrame(columns=FIT_COLUMNS)
    races = (
        microsectors.groupby(
            ["season", "round", "race_name", "driver_code", "driver_name"], as_index=False
        )["segment_delta_sec"]
        .sum()
        .rename(columns={"segment_delta_sec": "race_gain_sec"})
    )
    races = races.merge(
        archetypes[["season", "round", "circuit_archetype"]],
        on=["season", "round"],
        how="inner",
    )
    rows: list[dict[str, object]] = []
    for (driver_code, driver_name, archetype), group in races.groupby(
        ["driver_code", "driver_name", "circuit_archetype"], sort=True
    ):
        median = float(group["race_gain_sec"].median())
        agreement = float((np.sign(group["race_gain_sec"]) == np.sign(median)).mean() * 100)
        count = len(group)
        rows.append(
            {
                "driver_code": driver_code,
                "driver_name": driver_name,
                "circuit_archetype": archetype,
                "n_races": count,
                "median_gain_sec": median,
                "mean_gain_sec": float(group["race_gain_sec"].mean()),
                "gain_direction_agreement_pct": agreement,
                "confidence": "strong" if count >= 5 else "limited",
                "methodology_version": METHODOLOGY_VERSION,
            }
        )
    return pd.DataFrame(rows, columns=FIT_COLUMNS)


def analyse_driver_track(evidence: pd.DataFrame, microsectors: pd.DataFrame) -> DriverTrackResult:
    """Build circuit, driver-fit and stability outputs from Driver DNA evidence."""
    archetypes = classify_circuit_archetypes(microsectors)
    fit = build_driver_track_fit(microsectors, archetypes)
    stability = build_stability_windows(evidence)
    return DriverTrackResult(archetypes, fit, stability)


def validate_driver_track(result: DriverTrackResult) -> None:
    """Reject non-finite or duplicate publishable driver-track rows."""
    if not result.archetypes.empty:
        if result.archetypes.duplicated(["season", "round"]).any():
            raise ValueError("circuit archetypes are not unique by race")
        numeric = [
            "average_speed_kph",
            "braking_density_pct",
            "full_throttle_pct",
            "low_speed_segment_pct",
        ]
        if not np.isfinite(result.archetypes[numeric].to_numpy(dtype=float)).all():
            raise ValueError("circuit archetypes contain non-finite features")
    if (
        not result.driver_fit.empty
        and result.driver_fit.duplicated(["driver_code", "circuit_archetype"]).any()
    ):
        raise ValueError("driver-track fit rows are not unique")
    if (
        not result.dna_stability.empty
        and result.dna_stability.duplicated(
            ["from_season", "to_season", "driver_code", "metric"]
        ).any()
    ):
        raise ValueError("Driver DNA stability rows are not unique by season window")
