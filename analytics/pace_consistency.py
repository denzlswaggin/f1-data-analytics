"""Driver pace consistency after controlling clean-air stint evolution.

The analysis is deliberately descriptive.  It models the normal tyre-life
trend inside each sufficiently observed clean-air stint, then measures the
remaining lap-to-lap dispersion and slow tail.  A large residual is not called
a driver mistake because timing data cannot observe every cause.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

METHODOLOGY_VERSION = "pace-consistency-v2-pit-context"
MIN_STINT_CLEAN_LAPS = 5
MIN_TYRE_AGE_VALUES = 4
MIN_TYRE_AGE_SPAN = 4.0
MIN_PUBLISH_LAPS = 8
MIN_REPLAY_COVERAGE_PCT = 80.0
SLOW_LAP_FLOOR_SEC = 0.75
SLOW_LAP_LAP_TIME_SHARE = 0.01
ROBUST_SIGMA_SCALE = 1.4826

_DRIVER_KEYS = ["season", "round", "driver_code"]
_STINT_KEYS = [*_DRIVER_KEYS, "stint"]
_REQUIRED = {
    *_STINT_KEYS,
    "race_name",
    "driver_name",
    "team",
    "lap_number",
    "compound",
    "tyre_life",
    "lap_time_sec",
    "air_state",
    "replay_coverage_pct",
    "controlled_pace_delta_sec",
}

PACE_CONSISTENCY_COLUMNS = [
    "season",
    "round",
    "race_name",
    "driver_code",
    "driver_name",
    "team",
    "candidate_laps",
    "modelled_laps",
    "excluded_laps",
    "candidate_stints",
    "modelled_stints",
    "robust_consistency_sec",
    "robust_consistency_pct",
    "p90_slow_tail_sec",
    "slow_lap_threshold_sec",
    "unexplained_slow_laps",
    "unexplained_slow_lap_share_pct",
    "unexplained_slow_lap_cost_sec",
    "slow_lap_cost_per_10_laps_sec",
    "worst_residual_sec",
    "replay_coverage_pct",
    "consistency_eligible",
    "exclusion_reason",
    "confidence",
    "methodology_version",
]

PACE_CONSISTENCY_LAP_COLUMNS = [
    "season",
    "round",
    "race_name",
    "driver_code",
    "driver_name",
    "team",
    "lap_number",
    "stint",
    "compound",
    "tyre_life",
    "lap_time_sec",
    "air_state",
    "replay_coverage_pct",
    "controlled_pace_delta_sec",
    "expected_controlled_pace_delta_sec",
    "pace_residual_sec",
    "absolute_residual_sec",
    "slow_lap_threshold_sec",
    "unexplained_slow_excess_sec",
    "is_unexplained_slow_lap",
    "lap_eligible",
    "lap_exclusion_reason",
    "stint_clean_laps",
    "stint_slope_sec_per_tyre_lap",
    "stint_intercept_sec",
    "methodology_version",
]

_SUMMARY_INTEGER = {
    "season",
    "round",
    "candidate_laps",
    "modelled_laps",
    "excluded_laps",
    "candidate_stints",
    "modelled_stints",
    "unexplained_slow_laps",
}
_SUMMARY_FLOAT = {
    "robust_consistency_sec",
    "robust_consistency_pct",
    "p90_slow_tail_sec",
    "slow_lap_threshold_sec",
    "unexplained_slow_lap_share_pct",
    "unexplained_slow_lap_cost_sec",
    "slow_lap_cost_per_10_laps_sec",
    "worst_residual_sec",
    "replay_coverage_pct",
}
_SUMMARY_BOOLEAN = {"consistency_eligible"}
_LAP_INTEGER = {"season", "round", "lap_number", "stint", "stint_clean_laps"}
_LAP_FLOAT = {
    "tyre_life",
    "lap_time_sec",
    "replay_coverage_pct",
    "controlled_pace_delta_sec",
    "expected_controlled_pace_delta_sec",
    "pace_residual_sec",
    "absolute_residual_sec",
    "unexplained_slow_excess_sec",
    "slow_lap_threshold_sec",
    "stint_slope_sec_per_tyre_lap",
    "stint_intercept_sec",
}
_LAP_BOOLEAN = {"is_unexplained_slow_lap", "lap_eligible"}


@dataclass(frozen=True)
class PaceConsistencyResult:
    """Driver-race conclusions and their lap-level evidence."""

    summary: pd.DataFrame
    laps: pd.DataFrame


def _typed_empty(
    columns: list[str], integers: set[str], floats: set[str], booleans: set[str]
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            column: pd.Series(
                dtype=(
                    "Int64"
                    if column in integers
                    else "float64"
                    if column in floats
                    else "boolean"
                    if column in booleans
                    else "string"
                )
            )
            for column in columns
        }
    )


def _empty_result() -> PaceConsistencyResult:
    return PaceConsistencyResult(
        summary=_typed_empty(
            PACE_CONSISTENCY_COLUMNS,
            _SUMMARY_INTEGER,
            _SUMMARY_FLOAT,
            _SUMMARY_BOOLEAN,
        ),
        laps=_typed_empty(
            PACE_CONSISTENCY_LAP_COLUMNS,
            _LAP_INTEGER,
            _LAP_FLOAT,
            _LAP_BOOLEAN,
        ),
    )


def _require_columns(frame: pd.DataFrame) -> None:
    missing = _REQUIRED - set(frame.columns)
    if missing:
        raise ValueError(f"traffic_laps is missing columns: {sorted(missing)}")


def _theil_sen(x: pd.Series, y: pd.Series) -> tuple[float, float]:
    """Return a robust slope and intercept without requiring SciPy."""
    x_values = x.to_numpy(dtype=float)
    y_values = y.to_numpy(dtype=float)
    slopes: list[float] = []
    for left in range(len(x_values) - 1):
        delta_x = x_values[left + 1 :] - x_values[left]
        usable = delta_x != 0
        if usable.any():
            delta_y = y_values[left + 1 :] - y_values[left]
            slopes.extend((delta_y[usable] / delta_x[usable]).tolist())
    slope = float(np.median(slopes))
    intercept = float(np.median(y_values - slope * x_values))
    return slope, intercept


def _prepare_laps(traffic_laps: pd.DataFrame, min_replay_coverage_pct: float) -> pd.DataFrame:
    laps = traffic_laps.copy()
    numeric = [
        "season",
        "round",
        "lap_number",
        "stint",
        "tyre_life",
        "lap_time_sec",
        "replay_coverage_pct",
        "controlled_pace_delta_sec",
    ]
    for column in numeric:
        laps[column] = pd.to_numeric(laps[column], errors="coerce")
    laps = laps.dropna(subset=[*_STINT_KEYS, "lap_number"])
    duplicate = laps.duplicated(subset=[*_STINT_KEYS, "lap_number"], keep=False)
    if duplicate.any():
        raise ValueError("traffic_laps contains duplicate driver-stint-lap rows")
    laps[numeric] = laps[numeric].replace([np.inf, -np.inf], np.nan)

    complete = (
        laps[["tyre_life", "lap_time_sec", "replay_coverage_pct", "controlled_pace_delta_sec"]]
        .notna()
        .all(axis=1)
    )
    positive = laps["lap_time_sec"].gt(0)
    covered = laps["replay_coverage_pct"].ge(min_replay_coverage_pct)
    clean = laps["air_state"].eq("clean_air")
    laps["candidate"] = complete & positive & covered & clean
    laps["lap_exclusion_reason"] = np.select(
        [
            ~complete | ~positive,
            ~covered,
            laps["air_state"].eq("traffic"),
            ~clean,
        ],
        ["missing_or_invalid_timing", "replay_under_covered", "traffic_exposed", "mixed_air"],
        default="candidate",
    )
    return laps.sort_values([*_STINT_KEYS, "lap_number"]).reset_index(drop=True)


def _model_stints(
    laps: pd.DataFrame,
    *,
    min_stint_clean_laps: int,
    min_tyre_age_values: int,
    min_tyre_age_span: float,
) -> pd.DataFrame:
    out = laps.copy()
    out["stint_clean_laps"] = 0
    out["stint_slope_sec_per_tyre_lap"] = np.nan
    out["stint_intercept_sec"] = np.nan
    out["expected_controlled_pace_delta_sec"] = np.nan
    out["pace_residual_sec"] = np.nan
    out["absolute_residual_sec"] = np.nan
    out["unexplained_slow_excess_sec"] = np.nan
    out["is_unexplained_slow_lap"] = False
    out["lap_eligible"] = False

    for _, stint in out.groupby(_STINT_KEYS, sort=False, dropna=False):
        candidate = stint.loc[stint["candidate"]]
        indices = stint.index
        out.loc[indices, "stint_clean_laps"] = len(candidate)
        if len(candidate) < min_stint_clean_laps:
            mask = out.index.isin(candidate.index)
            out.loc[mask, "lap_exclusion_reason"] = "insufficient_stint_clean_laps"
            continue
        if candidate["tyre_life"].nunique() < min_tyre_age_values:
            mask = out.index.isin(candidate.index)
            out.loc[mask, "lap_exclusion_reason"] = "insufficient_tyre_age_variation"
            continue
        if float(candidate["tyre_life"].max() - candidate["tyre_life"].min()) < min_tyre_age_span:
            mask = out.index.isin(candidate.index)
            out.loc[mask, "lap_exclusion_reason"] = "insufficient_tyre_age_span"
            continue
        if candidate["compound"].nunique(dropna=True) != 1:
            mask = out.index.isin(candidate.index)
            out.loc[mask, "lap_exclusion_reason"] = "compound_changed_within_stint"
            continue

        slope, intercept = _theil_sen(
            candidate["tyre_life"], candidate["controlled_pace_delta_sec"]
        )
        expected = intercept + slope * candidate["tyre_life"]
        residual = candidate["controlled_pace_delta_sec"] - expected
        centre = float(residual.median())
        intercept += centre
        expected += centre
        residual -= centre
        out.loc[indices, "stint_slope_sec_per_tyre_lap"] = slope
        out.loc[indices, "stint_intercept_sec"] = intercept
        out.loc[candidate.index, "expected_controlled_pace_delta_sec"] = expected
        out.loc[candidate.index, "pace_residual_sec"] = residual
        out.loc[candidate.index, "absolute_residual_sec"] = residual.abs()
        out.loc[candidate.index, "lap_eligible"] = True
        out.loc[candidate.index, "lap_exclusion_reason"] = ""
    return out


def _add_slow_tail(
    laps: pd.DataFrame,
    *,
    slow_lap_floor_sec: float,
    slow_lap_lap_time_share: float,
) -> pd.DataFrame:
    out = laps.copy()
    out["slow_lap_threshold_sec"] = np.nan
    for _, driver_laps in out.groupby(_DRIVER_KEYS, sort=False, dropna=False):
        modelled = driver_laps.loc[driver_laps["lap_eligible"]]
        if modelled.empty:
            continue
        threshold = max(
            slow_lap_floor_sec,
            slow_lap_lap_time_share * float(modelled["lap_time_sec"].median()),
        )
        out.loc[driver_laps.index, "slow_lap_threshold_sec"] = threshold
        residual = modelled["pace_residual_sec"]
        excess = (residual - threshold).clip(lower=0)
        out.loc[modelled.index, "unexplained_slow_excess_sec"] = excess
        out.loc[modelled.index, "is_unexplained_slow_lap"] = residual.gt(threshold)
    return out


def _confidence(
    modelled_laps: int,
    modelled_stints: int,
    replay_coverage_pct: float,
    min_publish_laps: int,
) -> str:
    if modelled_laps < min_publish_laps:
        return "insufficient"
    if modelled_laps >= 20 and modelled_stints >= 2 and replay_coverage_pct >= 95:
        return "high"
    enough_medium_samples = (modelled_laps >= 12 and modelled_stints >= 2) or (
        modelled_laps >= 15 and modelled_stints == 1
    )
    if enough_medium_samples and replay_coverage_pct >= 90:
        return "medium"
    return "low"


def _summarise(
    laps: pd.DataFrame,
    *,
    min_publish_laps: int,
) -> pd.DataFrame:
    keys = ["season", "round", "race_name", "driver_code", "driver_name", "team"]
    rows: list[dict[str, object]] = []
    for key, driver_laps in laps.groupby(keys, sort=True, dropna=False):
        candidate = driver_laps.loc[driver_laps["candidate"]]
        modelled = driver_laps.loc[driver_laps["lap_eligible"]]
        modelled_stints = int(modelled["stint"].nunique())
        publish = len(modelled) >= min_publish_laps
        residual = modelled["pace_residual_sec"]
        median_residual = float(residual.median()) if publish else np.nan
        mad = float((residual - median_residual).abs().median()) if publish else np.nan
        slow = modelled.loc[modelled["is_unexplained_slow_lap"]]
        coverage = float(modelled["replay_coverage_pct"].median()) if len(modelled) else np.nan
        median_lap_time = float(modelled["lap_time_sec"].median()) if publish else np.nan
        consistency = ROBUST_SIGMA_SCALE * mad if publish else np.nan
        threshold = float(modelled["slow_lap_threshold_sec"].iloc[0]) if len(modelled) else np.nan
        if not len(candidate):
            exclusion_reason = "no_clean_air_evidence"
        elif not len(modelled):
            exclusion_reason = "no_valid_stint"
        elif not publish:
            exclusion_reason = "insufficient_modelled_laps"
        else:
            exclusion_reason = ""
        rows.append(
            {
                "season": key[0],
                "round": key[1],
                "race_name": key[2],
                "driver_code": key[3],
                "driver_name": key[4],
                "team": key[5],
                "candidate_laps": len(candidate),
                "modelled_laps": len(modelled),
                "excluded_laps": len(driver_laps) - len(modelled),
                "candidate_stints": int(candidate["stint"].nunique()),
                "modelled_stints": modelled_stints,
                "robust_consistency_sec": consistency,
                "robust_consistency_pct": (
                    100.0 * consistency / median_lap_time if publish else np.nan
                ),
                "p90_slow_tail_sec": float(residual.quantile(0.90)) if publish else np.nan,
                "slow_lap_threshold_sec": threshold,
                "unexplained_slow_laps": len(slow),
                "unexplained_slow_lap_share_pct": (
                    100.0 * len(slow) / len(modelled) if publish else np.nan
                ),
                "unexplained_slow_lap_cost_sec": (
                    float(modelled["unexplained_slow_excess_sec"].sum()) if publish else np.nan
                ),
                "slow_lap_cost_per_10_laps_sec": (
                    10.0 * float(modelled["unexplained_slow_excess_sec"].sum()) / len(modelled)
                    if publish
                    else np.nan
                ),
                "worst_residual_sec": float(residual.max()) if publish else np.nan,
                "replay_coverage_pct": coverage,
                "consistency_eligible": publish,
                "exclusion_reason": exclusion_reason,
                "confidence": _confidence(
                    len(modelled), modelled_stints, coverage, min_publish_laps
                ),
                "methodology_version": METHODOLOGY_VERSION,
            }
        )
    return pd.DataFrame(rows, columns=PACE_CONSISTENCY_COLUMNS)


def analyse_pace_consistency(
    traffic_laps: pd.DataFrame,
    *,
    min_stint_clean_laps: int = MIN_STINT_CLEAN_LAPS,
    min_tyre_age_values: int = MIN_TYRE_AGE_VALUES,
    min_tyre_age_span: float = MIN_TYRE_AGE_SPAN,
    min_publish_laps: int = MIN_PUBLISH_LAPS,
    min_replay_coverage_pct: float = MIN_REPLAY_COVERAGE_PCT,
    slow_lap_floor_sec: float = SLOW_LAP_FLOOR_SEC,
    slow_lap_lap_time_share: float = SLOW_LAP_LAP_TIME_SHARE,
) -> PaceConsistencyResult:
    """Measure repeatability and slow-tail cost on modelled clean-air laps."""
    _require_columns(traffic_laps)
    if (
        min_stint_clean_laps < 3
        or min_tyre_age_values < 2
        or min_tyre_age_span <= 0
        or min_publish_laps < 1
    ):
        raise ValueError("lap and tyre-age thresholds are below their supported minimum")
    if min_replay_coverage_pct <= 0 or min_replay_coverage_pct > 100:
        raise ValueError("min_replay_coverage_pct must be in (0, 100]")
    if slow_lap_floor_sec <= 0 or slow_lap_lap_time_share <= 0:
        raise ValueError("slow-lap threshold settings must be positive")
    if traffic_laps.empty:
        return _empty_result()

    laps = _prepare_laps(traffic_laps, min_replay_coverage_pct)
    if laps.empty:
        return _empty_result()
    laps = _model_stints(
        laps,
        min_stint_clean_laps=min_stint_clean_laps,
        min_tyre_age_values=min_tyre_age_values,
        min_tyre_age_span=min_tyre_age_span,
    )
    laps = _add_slow_tail(
        laps,
        slow_lap_floor_sec=slow_lap_floor_sec,
        slow_lap_lap_time_share=slow_lap_lap_time_share,
    )
    summary = _summarise(
        laps,
        min_publish_laps=min_publish_laps,
    )
    evidence = laps.assign(methodology_version=METHODOLOGY_VERSION).loc[
        :, PACE_CONSISTENCY_LAP_COLUMNS
    ]
    return PaceConsistencyResult(
        summary=summary.reset_index(drop=True),
        laps=evidence.reset_index(drop=True),
    )
