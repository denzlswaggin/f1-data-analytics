"""Stability and negative-control diagnostics for Driver DNA profiles."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from analytics.driver_dna import METHODOLOGY_VERSION, METRICS, analyse_driver_dna

STABILITY_COLUMNS = [
    "from_season",
    "to_season",
    "driver_code",
    "driver_name",
    "metric",
    "n_races",
    "full_estimate",
    "early_estimate",
    "late_estimate",
    "split_delta",
    "leave_one_out_max_delta",
    "sign_agreement_pct",
    "stable",
    "methodology_version",
]


@dataclass(frozen=True)
class DriverDNAValidationResult:
    stability: pd.DataFrame
    tolerance_sensitivity: pd.DataFrame
    negative_control: pd.DataFrame


def profile_stability(evidence: pd.DataFrame, *, min_races: int = 5) -> pd.DataFrame:
    """Measure split-sample and leave-one-race-out profile stability."""
    if evidence.empty:
        return pd.DataFrame(columns=STABILITY_COLUMNS)
    eligible = evidence[evidence["eligible"].fillna(False)].copy()
    if eligible.empty:
        return pd.DataFrame(columns=STABILITY_COLUMNS)
    from_season = int(eligible["season"].min())
    to_season = int(eligible["season"].max())
    rows: list[dict[str, object]] = []
    for driver_code, group in eligible.groupby("driver_code", sort=True):
        group = group.sort_values(["season", "round"])
        race_keys = list(group[["season", "round"]].drop_duplicates().itertuples(index=False))
        midpoint = len(race_keys) // 2
        early_keys = set(race_keys[:midpoint])
        late_keys = set(race_keys[midpoint:])
        keys = list(group[["season", "round"]].itertuples(index=False))
        early = group[[key in early_keys for key in keys]]
        late = group[[key in late_keys for key in keys]]
        for metric in METRICS:
            column = f"{metric}_z"
            full = float(group[column].median())
            early_value = float(early[column].median()) if not early.empty else float("nan")
            late_value = float(late[column].median()) if not late.empty else float("nan")
            leave_one_out = []
            for key in race_keys:
                remaining = group[
                    ~((group["season"] == key.season) & (group["round"] == key.round))
                ]
                if not remaining.empty:
                    leave_one_out.append(abs(float(remaining[column].median()) - full))
            nonzero = group[column].dropna()
            sign_agreement = (
                float((np.sign(nonzero) == np.sign(full)).mean() * 100) if full != 0 else 100.0
            )
            split_delta = abs(early_value - late_value)
            loo_delta = max(leave_one_out, default=float("nan"))
            stable = bool(
                len(race_keys) >= min_races
                and np.isfinite(split_delta)
                and split_delta <= 1.0
                and np.isfinite(loo_delta)
                and loo_delta <= 0.75
                and sign_agreement >= 60.0
            )
            rows.append(
                {
                    "from_season": from_season,
                    "to_season": to_season,
                    "driver_code": driver_code,
                    "driver_name": group["driver_name"].dropna().iloc[0],
                    "metric": metric,
                    "n_races": len(race_keys),
                    "full_estimate": full,
                    "early_estimate": early_value,
                    "late_estimate": late_value,
                    "split_delta": split_delta,
                    "leave_one_out_max_delta": loo_delta,
                    "sign_agreement_pct": sign_agreement,
                    "stable": stable,
                    "methodology_version": METHODOLOGY_VERSION,
                }
            )
    return pd.DataFrame(rows, columns=STABILITY_COLUMNS)


def build_stability_windows(evidence: pd.DataFrame, *, min_races: int = 5) -> pd.DataFrame:
    """Publish stability diagnostics for every contiguous available season window."""
    if evidence.empty:
        return pd.DataFrame(columns=STABILITY_COLUMNS)
    eligible = evidence[evidence["eligible"].fillna(False)]
    seasons = sorted(int(season) for season in eligible["season"].dropna().unique())
    frames: list[pd.DataFrame] = []
    for start_index, from_season in enumerate(seasons):
        for to_season in seasons[start_index:]:
            scoped = evidence[evidence["season"].between(from_season, to_season)]
            stability = profile_stability(scoped, min_races=min_races)
            if not stability.empty:
                stability["from_season"] = from_season
                stability["to_season"] = to_season
                frames.append(stability)
    return (
        pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=STABILITY_COLUMNS)
    )


def permutation_negative_control(
    evidence: pd.DataFrame,
    *,
    n_permutations: int = 200,
    seed: int = 0,
) -> pd.DataFrame:
    """Compare between-driver separation with shuffled driver labels."""
    eligible = evidence[evidence["eligible"].fillna(False)].copy()
    if eligible.empty:
        return pd.DataFrame(
            columns=[
                "metric",
                "observed_driver_spread",
                "shuffled_median_spread",
                "signal_to_null_ratio",
                "permutations",
                "methodology_version",
            ]
        )
    rng = np.random.default_rng(seed)
    labels = eligible["driver_code"].to_numpy(copy=True)
    rows: list[dict[str, object]] = []
    for metric in METRICS:
        column = f"{metric}_z"
        observed = float(eligible.groupby("driver_code")[column].median().std(ddof=0))
        shuffled: list[float] = []
        for _ in range(n_permutations):
            frame = eligible[[column]].copy()
            frame["driver_code"] = rng.permutation(labels)
            shuffled.append(float(frame.groupby("driver_code")[column].median().std(ddof=0)))
        null_spread = float(np.nanmedian(shuffled))
        ratio = observed / null_spread if null_spread > 0 else float("nan")
        rows.append(
            {
                "metric": metric,
                "observed_driver_spread": observed,
                "shuffled_median_spread": null_spread,
                "signal_to_null_ratio": ratio,
                "permutations": n_permutations,
                "methodology_version": METHODOLOGY_VERSION,
            }
        )
    return pd.DataFrame(rows)


def tolerance_sensitivity(
    telemetry: pd.DataFrame,
    laps: pd.DataFrame,
    *,
    tolerances: tuple[tuple[int, int], ...] = ((1, 2), (3, 3), (5, 5)),
) -> pd.DataFrame:
    """Re-run pair selection across declared lap/tyre-age tolerance choices."""
    rows: list[dict[str, object]] = []
    for lap_gap, tyre_gap in tolerances:
        result = analyse_driver_dna(
            telemetry,
            laps,
            n_boot=0,
            max_lap_gap=lap_gap,
            max_tyre_life_gap=tyre_gap,
        )
        eligible = result.evidence[result.evidence["eligible"].fillna(False)]
        rows.append(
            {
                "max_lap_gap": lap_gap,
                "max_tyre_life_gap": tyre_gap,
                "eligible_pairs": len(eligible) // 2,
                "drivers": int(eligible["driver_code"].nunique()),
                "races": int(eligible[["season", "round"]].drop_duplicates().shape[0]),
                "methodology_version": METHODOLOGY_VERSION,
            }
        )
    return pd.DataFrame(rows)


def validate_driver_dna_stability(
    evidence: pd.DataFrame,
    telemetry: pd.DataFrame,
    laps: pd.DataFrame,
    *,
    n_permutations: int = 200,
    seed: int = 0,
) -> DriverDNAValidationResult:
    """Run the complete non-causal Driver DNA robustness battery."""
    return DriverDNAValidationResult(
        stability=profile_stability(evidence),
        tolerance_sensitivity=tolerance_sensitivity(telemetry, laps),
        negative_control=permutation_negative_control(
            evidence, n_permutations=n_permutations, seed=seed
        ),
    )
