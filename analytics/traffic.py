"""Traffic-adjusted race pace from green-flag laps and replay gaps.

The output is descriptive, not causal. A short reconstructed gap is a useful
proxy for traffic, but it cannot prove that dirty air caused the whole observed
lap-time difference. The method controls the largest visible confounders and
publishes its coverage and sample size alongside every result.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TRAFFIC_GAP_S = 1.5
CLEAN_AIR_GAP_S = 3.0
TRAFFIC_LAP_SHARE = 0.50
CLEAN_AIR_LAP_SHARE = 0.80
MAX_CLEAN_LAP_TRAFFIC_SHARE = 0.10
MIN_REPLAY_COVERAGE = 0.80
TYRE_AGE_WINDOW = 2.0
MIN_PUBLISH_LAPS = 5
MIN_PEER_DRIVERS = 3

_LAP_KEYS = ["season", "round", "driver_code", "lap_number"]
_DRIVER_KEYS = ["season", "round", "driver_code"]
_LAP_REQUIRED = {
    *_LAP_KEYS,
    "race_name",
    "team",
    "stint",
    "compound",
    "tyre_life",
    "lap_time_sec",
}
_REPLAY_REQUIRED = {
    *_LAP_KEYS,
    "t_s",
    "running_order",
    "gap_to_ahead_s",
    "stint",
}

_EVIDENCE_COLUMNS = [
    "season",
    "round",
    "race_name",
    "driver_code",
    "team",
    "lap_number",
    "stint",
    "compound",
    "tyre_life",
    "lap_time_sec",
    "context_samples",
    "valid_context_samples",
    "traffic_samples",
    "traffic_share",
    "clean_air_share",
    "replay_coverage_pct",
    "median_gap_to_ahead_s",
    "air_state",
    "peer_lap_avg_sec",
    "peer_lap_median_sec",
    "peer_count",
    "controlled_pace_delta_sec",
    "matched_clean_laps",
    "matched_clean_delta_sec",
    "paired_traffic_delta_sec",
]

_SUMMARY_COLUMNS = [
    "season",
    "round",
    "race_name",
    "driver_code",
    "team",
    "eligible_laps",
    "clean_air_laps",
    "traffic_laps",
    "mixed_laps",
    "matched_traffic_laps",
    "traffic_exposure_pct",
    "replay_coverage_pct",
    "observed_controlled_pace_delta_sec",
    "clean_air_controlled_pace_delta_sec",
    "traffic_adjusted_pace_delta_sec",
    "traffic_controlled_pace_delta_sec",
    "traffic_associated_delta_sec_per_lap",
    "traffic_associated_p25_sec",
    "traffic_associated_p75_sec",
    "confidence",
    "clean_air_eligible",
    "clean_air_confidence",
    "traffic_association_eligible",
    "traffic_association_confidence",
    "traffic_gap_threshold_s",
    "clean_air_gap_threshold_s",
    "methodology_version",
]


@dataclass(frozen=True)
class TrafficPaceResult:
    """Lap evidence and one driver summary for each race."""

    evidence: pd.DataFrame
    summary: pd.DataFrame


def _require_columns(frame: pd.DataFrame, required: set[str], name: str) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{name} is missing columns: {sorted(missing)}")


def _empty_result() -> TrafficPaceResult:
    text_columns = {
        "race_name",
        "driver_code",
        "team",
        "confidence",
        "clean_air_confidence",
        "traffic_association_confidence",
        "methodology_version",
    }
    integer_columns = {
        "season",
        "round",
        "eligible_laps",
        "clean_air_laps",
        "traffic_laps",
        "mixed_laps",
        "matched_traffic_laps",
    }
    boolean_columns = {"clean_air_eligible", "traffic_association_eligible"}
    summary = pd.DataFrame(
        {
            column: pd.Series(
                dtype="string"
                if column in text_columns
                else "int64"
                if column in integer_columns
                else "bool"
                if column in boolean_columns
                else "float64"
            )
            for column in _SUMMARY_COLUMNS
        }
    )
    return TrafficPaceResult(
        evidence=pd.DataFrame(columns=_EVIDENCE_COLUMNS).astype(
            {"peer_lap_median_sec": "float64", "peer_count": "int64"}
        ),
        summary=summary,
    )


def _lap_context(
    replay: pd.DataFrame,
    lap_durations: pd.DataFrame,
    *,
    traffic_gap_s: float,
    clean_air_gap_s: float,
) -> pd.DataFrame:
    """Collapse replay ticks into coverage and air-state evidence by lap."""
    output_columns = [
        *_LAP_KEYS,
        "context_samples",
        "valid_context_samples",
        "traffic_samples",
        "traffic_share",
        "clean_air_share",
        "replay_coverage_pct",
        "median_gap_to_ahead_s",
    ]
    context = replay.dropna(subset=[*_LAP_KEYS, "t_s", "running_order"]).copy()
    if context.empty:
        return pd.DataFrame(columns=output_columns)

    context = context.drop_duplicates(subset=[*_LAP_KEYS, "t_s"])
    context["t_s"] = pd.to_numeric(context["t_s"], errors="coerce")
    context = context.dropna(subset=["t_s"]).sort_values([*_DRIVER_KEYS, "t_s"])
    context["sample_interval_s"] = context.groupby(_DRIVER_KEYS)["t_s"].diff()
    tick_interval = (
        context.loc[context["sample_interval_s"].gt(0)]
        .groupby(_DRIVER_KEYS, as_index=False)["sample_interval_s"]
        .median()
        .rename(columns={"sample_interval_s": "tick_interval_s"})
    )
    context = context.merge(lap_durations, on=_LAP_KEYS, how="inner", validate="many_to_one")
    context = context.merge(tick_interval, on=_DRIVER_KEYS, how="left", validate="many_to_one")
    if context.empty:
        return pd.DataFrame(columns=output_columns)

    # The final completed lap can linger in the replay after the timing feed has
    # stopped. Cap each lap at one observed lap duration from its first sample.
    first_tick = context.groupby(_LAP_KEYS)["t_s"].transform("min")
    context = context.loc[
        context["t_s"].sub(first_tick).le(context["lap_time_sec"] + context["tick_interval_s"])
    ].copy()

    order = pd.to_numeric(context["running_order"], errors="coerce")
    gap = pd.to_numeric(context["gap_to_ahead_s"], errors="coerce")
    follower = order.gt(1)
    context["valid_tick"] = order.eq(1) | (follower & gap.gt(0))
    context["traffic_tick"] = follower & gap.gt(0) & gap.le(traffic_gap_s)
    context["clean_air_tick"] = order.eq(1) | (follower & gap.ge(clean_air_gap_s))
    context["follower_gap_s"] = gap.where(follower & gap.gt(0))

    grouped = (
        context.groupby(_LAP_KEYS, as_index=False, dropna=False)
        .agg(
            context_samples=("t_s", "count"),
            valid_context_samples=("valid_tick", "sum"),
            traffic_samples=("traffic_tick", "sum"),
            clean_air_samples=("clean_air_tick", "sum"),
            median_gap_to_ahead_s=("follower_gap_s", "median"),
            tick_interval_s=("tick_interval_s", "median"),
            lap_time_sec=("lap_time_sec", "first"),
        )
        .sort_values(_LAP_KEYS)
    )
    valid = grouped["valid_context_samples"].replace(0, np.nan)
    grouped["traffic_share"] = grouped["traffic_samples"] / valid
    grouped["clean_air_share"] = grouped["clean_air_samples"] / valid
    grouped["replay_coverage_pct"] = (
        100 * grouped["context_samples"] * grouped["tick_interval_s"] / grouped["lap_time_sec"]
    ).clip(upper=100)
    return grouped.loc[:, output_columns].reset_index(drop=True)


def _stint_bounds(replay: pd.DataFrame) -> pd.DataFrame:
    """Return all-lap stint boundaries, including non-green pit transitions."""
    columns = [*_DRIVER_KEYS, "stint", "stint_first_lap", "stint_last_lap", "last_stint"]
    source = replay.dropna(subset=[*_LAP_KEYS, "stint"]).copy()
    if source.empty:
        return pd.DataFrame(columns=columns)
    stint_keys = [*_DRIVER_KEYS, "stint"]
    bounds = (
        source.groupby(stint_keys, as_index=False)["lap_number"]
        .agg(stint_first_lap="min", stint_last_lap="max")
        .sort_values(stint_keys)
    )
    bounds["last_stint"] = bounds.groupby(_DRIVER_KEYS)["stint"].transform("max")
    return bounds.loc[:, columns]


def _exclude_non_representative_laps(laps: pd.DataFrame, replay: pd.DataFrame) -> pd.DataFrame:
    """Remove lap one, pit transitions, immature tyres and unknown compounds."""
    out = laps.merge(
        _stint_bounds(replay),
        on=[*_DRIVER_KEYS, "stint"],
        how="left",
        validate="many_to_one",
    )
    is_start = out["lap_number"].le(1)
    is_out_lap = out["lap_number"].eq(out["stint_first_lap"]) & out["stint"].gt(1)
    is_in_lap = out["lap_number"].eq(out["stint_last_lap"]) & out["stint"].lt(out["last_stint"])
    pit_boundary = out.get("is_pit_boundary", pd.Series(False, index=out.index)).fillna(False)
    known_compound = out["compound"].astype(str).str.strip().str.upper().ne("UNKNOWN")
    known_compound &= out["compound"].astype(str).str.strip().ne("")
    mature_tyre = out["tyre_life"].ge(2)
    return out.loc[
        ~(is_start | is_out_lap | is_in_lap | pit_boundary) & known_compound & mature_tyre
    ].drop(columns=["stint_first_lap", "stint_last_lap", "last_stint"])


def _add_controlled_delta(
    laps: pd.DataFrame, min_peer_drivers: int = MIN_PEER_DRIVERS
) -> pd.DataFrame:
    """Use a leave-one-driver-out median; retain the mean only as a diagnostic."""
    _validate_peer_minimum(min_peer_drivers)
    peers = ["season", "round", "lap_number", "compound"]
    out = laps.copy()
    if out.duplicated(_LAP_KEYS).any():
        raise ValueError("laps must contain one observation per driver and lap")
    grouped = out.groupby(peers)["lap_time_sec"]
    out["peer_count"] = grouped.transform("count") - 1
    out["peer_lap_avg_sec"] = (grouped.transform("sum") - out["lap_time_sec"]) / out["peer_count"]
    out["peer_lap_median_sec"] = grouped.transform(
        lambda values: pd.Series(
            [
                float(np.median(np.delete(values.to_numpy(), index))) if len(values) > 1 else np.nan
                for index in range(len(values))
            ],
            index=values.index,
        )
    )
    out = out.loc[out["peer_count"].ge(min_peer_drivers)].copy()
    out["controlled_pace_delta_sec"] = out["lap_time_sec"] - out["peer_lap_median_sec"]
    return out


def _validate_peer_minimum(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 2:
        raise ValueError("min_peer_drivers must be an integer >= 2")


def _match_clean_air_laps(laps: pd.DataFrame, tyre_age_window: float) -> pd.DataFrame:
    """Match traffic laps to all comparable clean laps, across stint numbers."""
    out = laps.copy()
    out["matched_clean_laps"] = 0
    out["matched_clean_delta_sec"] = np.nan
    out["paired_traffic_delta_sec"] = np.nan

    for _, driver_laps in out.groupby(_DRIVER_KEYS, sort=False):
        clean = driver_laps.loc[driver_laps["air_state"].eq("clean_air")]
        traffic = driver_laps.loc[driver_laps["air_state"].eq("traffic")]
        for idx, lap in traffic.iterrows():
            candidates = clean.loc[
                clean["compound"].eq(lap["compound"])
                & clean["tyre_life"].sub(lap["tyre_life"]).abs().le(tyre_age_window)
            ]
            if candidates.empty:
                continue
            clean_delta = float(candidates["controlled_pace_delta_sec"].median())
            out.loc[idx, "matched_clean_laps"] = len(candidates)
            out.loc[idx, "matched_clean_delta_sec"] = clean_delta
            out.loc[idx, "paired_traffic_delta_sec"] = float(
                lap["controlled_pace_delta_sec"] - clean_delta
            )
    return out


def classify_representative_lap_air(
    laps: pd.DataFrame,
    replay: pd.DataFrame,
    *,
    traffic_gap_s: float = TRAFFIC_GAP_S,
    clean_air_gap_s: float = CLEAN_AIR_GAP_S,
    traffic_lap_share: float = TRAFFIC_LAP_SHARE,
    clean_air_lap_share: float = CLEAN_AIR_LAP_SHARE,
    max_clean_lap_traffic_share: float = MAX_CLEAN_LAP_TRAFFIC_SHARE,
    min_replay_coverage: float = MIN_REPLAY_COVERAGE,
) -> pd.DataFrame:
    """Attach replay air state before any same-compound peer filtering.

    This public intermediate is useful when another analysis needs the same
    representative-lap and replay-coverage rules but must retain all compounds.
    """
    _require_columns(laps, _LAP_REQUIRED, "laps")
    _require_columns(replay, _REPLAY_REQUIRED, "replay")
    if traffic_gap_s <= 0 or clean_air_gap_s <= traffic_gap_s:
        raise ValueError("clean_air_gap_s must be greater than traffic_gap_s > 0")
    shares = (traffic_lap_share, clean_air_lap_share, max_clean_lap_traffic_share)
    if any(value < 0 or value > 1 for value in shares):
        raise ValueError("lap-share thresholds must be between 0 and 1")
    if min_replay_coverage <= 0 or min_replay_coverage > 1:
        raise ValueError("min_replay_coverage must be in (0, 1]")
    if laps.empty or replay.empty:
        return pd.DataFrame()

    pace = laps.copy()
    if pace.duplicated(_LAP_KEYS).any():
        raise ValueError("laps must contain one observation per driver and lap")
    for column in ("lap_number", "stint", "tyre_life", "lap_time_sec"):
        pace[column] = pd.to_numeric(pace[column], errors="coerce")
    pace = pace.dropna(
        subset=["lap_number", "stint", "tyre_life", "lap_time_sec", "driver_code", "compound"]
    )
    pace = pace.loc[pace["lap_time_sec"].gt(0) & np.isfinite(pace["lap_time_sec"])]
    pace = _exclude_non_representative_laps(pace, replay)

    lap_durations = pace.loc[:, [*_LAP_KEYS, "lap_time_sec"]].drop_duplicates(_LAP_KEYS)
    context = _lap_context(
        replay,
        lap_durations,
        traffic_gap_s=traffic_gap_s,
        clean_air_gap_s=clean_air_gap_s,
    )
    pace = pace.merge(context, on=_LAP_KEYS, how="inner", validate="one_to_one")
    if pace.empty:
        return pace

    enough_coverage = pace["replay_coverage_pct"].ge(100 * min_replay_coverage)
    pace["air_state"] = np.select(
        [
            enough_coverage & pace["traffic_share"].ge(traffic_lap_share),
            enough_coverage
            & pace["clean_air_share"].ge(clean_air_lap_share)
            & pace["traffic_share"].le(max_clean_lap_traffic_share),
        ],
        ["traffic", "clean_air"],
        default="mixed",
    )
    return pace


def _sample_strength(samples: int, min_publish_laps: int) -> str:
    """Heuristic sample strength, not calibrated statistical confidence."""
    if samples < min_publish_laps:
        return "insufficient"
    return "high" if samples >= 12 else "medium" if samples >= 8 else "low"


def _summarise(
    laps: pd.DataFrame,
    *,
    min_publish_laps: int,
    traffic_gap_s: float,
    clean_air_gap_s: float,
) -> pd.DataFrame:
    group_keys = ["season", "round", "race_name", "driver_code", "team"]
    rows: list[dict[str, object]] = []
    for key, driver_laps in laps.groupby(group_keys, sort=True, dropna=False):
        traffic = driver_laps.loc[driver_laps["air_state"].eq("traffic")]
        clean = driver_laps.loc[driver_laps["air_state"].eq("clean_air")]
        mixed = driver_laps.loc[driver_laps["air_state"].eq("mixed")]
        matched = traffic.dropna(subset=["paired_traffic_delta_sec"])
        publish_clean = len(clean) >= min_publish_laps
        publish_association = publish_clean and len(matched) >= min_publish_laps
        strength = min(len(clean), len(matched))
        clean_confidence = _sample_strength(len(clean), min_publish_laps)
        association_confidence = _sample_strength(strength, min_publish_laps)
        clean_delta = (
            float(clean["controlled_pace_delta_sec"].median()) if publish_clean else np.nan
        )
        association = matched["paired_traffic_delta_sec"]
        valid_samples = float(driver_laps["valid_context_samples"].sum())
        traffic_exposure = (
            100.0 * float(driver_laps["traffic_samples"].sum()) / valid_samples
            if valid_samples
            else np.nan
        )
        coverage_weight = float(driver_laps["lap_time_sec"].sum())
        replay_coverage = (
            float(
                (driver_laps["replay_coverage_pct"] * driver_laps["lap_time_sec"]).sum()
                / coverage_weight
            )
            if coverage_weight
            else np.nan
        )
        rows.append(
            {
                "season": key[0],
                "round": key[1],
                "race_name": key[2],
                "driver_code": key[3],
                "team": key[4],
                "eligible_laps": len(driver_laps),
                "clean_air_laps": len(clean),
                "traffic_laps": len(traffic),
                "mixed_laps": len(mixed),
                "matched_traffic_laps": len(matched),
                "traffic_exposure_pct": traffic_exposure,
                "replay_coverage_pct": replay_coverage,
                "observed_controlled_pace_delta_sec": driver_laps[
                    "controlled_pace_delta_sec"
                ].median(),
                "clean_air_controlled_pace_delta_sec": clean_delta,
                "traffic_adjusted_pace_delta_sec": clean_delta,
                "traffic_controlled_pace_delta_sec": traffic["controlled_pace_delta_sec"].median(),
                "traffic_associated_delta_sec_per_lap": (
                    association.median() if publish_association else np.nan
                ),
                "traffic_associated_p25_sec": (
                    association.quantile(0.25) if publish_association else np.nan
                ),
                "traffic_associated_p75_sec": (
                    association.quantile(0.75) if publish_association else np.nan
                ),
                # Retained for existing consumers: this alias describes only
                # the traffic association, never the clean-air estimate.
                "confidence": association_confidence,
                "clean_air_eligible": publish_clean,
                "clean_air_confidence": clean_confidence,
                "traffic_association_eligible": publish_association,
                "traffic_association_confidence": association_confidence,
                "traffic_gap_threshold_s": traffic_gap_s,
                "clean_air_gap_threshold_s": clean_air_gap_s,
                "methodology_version": "traffic-v4-robust-peers",
            }
        )
    return pd.DataFrame(rows, columns=_SUMMARY_COLUMNS)


def analyse_traffic_adjusted_pace(
    laps: pd.DataFrame,
    replay: pd.DataFrame,
    *,
    traffic_gap_s: float = TRAFFIC_GAP_S,
    clean_air_gap_s: float = CLEAN_AIR_GAP_S,
    traffic_lap_share: float = TRAFFIC_LAP_SHARE,
    clean_air_lap_share: float = CLEAN_AIR_LAP_SHARE,
    max_clean_lap_traffic_share: float = MAX_CLEAN_LAP_TRAFFIC_SHARE,
    min_replay_coverage: float = MIN_REPLAY_COVERAGE,
    tyre_age_window: float = TYRE_AGE_WINDOW,
    min_publish_laps: int = MIN_PUBLISH_LAPS,
    min_peer_drivers: int = MIN_PEER_DRIVERS,
) -> TrafficPaceResult:
    """Calculate clean-air observed pace and traffic-associated differences.

    A traffic lap spends at least half of its valid replay samples within
    ``traffic_gap_s`` of a car ahead. A clean lap spends at least 80% of them
    leading or beyond ``clean_air_gap_s``, with no more than 10% close traffic.
    Laps below the configured replay coverage are classified as mixed. Headline
    metrics remain null until their published sample threshold is met.
    Controlled deltas use the median of at least three other same-lap/compound
    drivers by default. This cutoff is a heuristic, not an externally validated
    guarantee of precision; two-peer sensitivity runs are explicitly opt-in.
    """
    if tyre_age_window < 0 or min_publish_laps < 1:
        raise ValueError("matching thresholds must be non-negative")
    _validate_peer_minimum(min_peer_drivers)
    pace = classify_representative_lap_air(
        laps,
        replay,
        traffic_gap_s=traffic_gap_s,
        clean_air_gap_s=clean_air_gap_s,
        traffic_lap_share=traffic_lap_share,
        clean_air_lap_share=clean_air_lap_share,
        max_clean_lap_traffic_share=max_clean_lap_traffic_share,
        min_replay_coverage=min_replay_coverage,
    )
    if pace.empty:
        return _empty_result()
    pace = _add_controlled_delta(pace, min_peer_drivers)
    if pace.empty:
        return _empty_result()
    pace = _match_clean_air_laps(pace, tyre_age_window)
    evidence = pace.loc[:, _EVIDENCE_COLUMNS].sort_values(
        ["season", "round", "driver_code", "lap_number"]
    )
    summary = _summarise(
        evidence,
        min_publish_laps=min_publish_laps,
        traffic_gap_s=traffic_gap_s,
        clean_air_gap_s=clean_air_gap_s,
    )
    return TrafficPaceResult(evidence=evidence.reset_index(drop=True), summary=summary)
