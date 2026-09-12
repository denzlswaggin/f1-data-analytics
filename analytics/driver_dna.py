"""Teammate-normalised fast-race-lap technique profiles.

Driver DNA intentionally describes *observed technique on representative fast
race laps*.  It is not a general driver-skill or causal car-performance model.
Only same-race, same-team and same-compound laps under green track status are
compared.  Every accepted comparison is stored in both directions so the
published deltas remain auditable and exactly antisymmetric.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np
import pandas as pd

METRICS = (
    "full_throttle_share",
    "coasting_share",
    "braking_share",
    "brake_onset_speed_kph",
    "low_speed_kph",
)
DRY_COMPOUNDS = {"SOFT", "MEDIUM", "HARD"}
METHODOLOGY_VERSION = "driver-dna-v2-joint-pairing"
MIN_COMMON_POINTS = 100
MIN_VALID_COVERAGE_PCT = 95.0
MICROSECTOR_LENGTH_M = 200.0
DEFAULT_MAX_LAP_GAP = 3
DEFAULT_MAX_TYRE_LIFE_GAP = 3


@dataclass(frozen=True)
class DriverDNAResult:
    """The three publishable Driver DNA marts."""

    evidence: pd.DataFrame
    profile: pd.DataFrame
    microsectors: pd.DataFrame


def validate_driver_dna(result: DriverDNAResult) -> None:
    """Raise when a Driver DNA result violates its publication contract."""
    eligible = result.evidence[result.evidence["eligible"].fillna(False)]
    if not eligible.empty:
        if (eligible["common_points"] < MIN_COMMON_POINTS).any():
            raise ValueError("eligible Driver DNA evidence has fewer than 100 common points")
        if (eligible["valid_coverage_pct"] < MIN_VALID_COVERAGE_PCT).any():
            raise ValueError("eligible Driver DNA evidence has invalid coverage below 95%")
        numeric = [
            *[f"{metric}_delta" for metric in METRICS],
            *[f"{metric}_z" for metric in METRICS],
        ]
        if not np.isfinite(eligible[numeric].to_numpy(dtype=float)).all():
            raise ValueError("eligible Driver DNA evidence contains non-finite metrics")
        lookup = eligible.set_index(["season", "round", "driver_code", "teammate_code"])
        for row in eligible.itertuples(index=False):
            reverse_key = (row.season, row.round, row.teammate_code, row.driver_code)
            if reverse_key not in lookup.index:
                raise ValueError("Driver DNA evidence is missing an antisymmetric reverse row")
            reverse = lookup.loc[reverse_key]
            for metric in METRICS:
                if not np.isclose(
                    float(getattr(row, f"{metric}_delta")),
                    -float(reverse[f"{metric}_delta"]),
                    atol=1e-10,
                ):
                    raise ValueError(f"Driver DNA {metric} delta is not antisymmetric")
    if not result.profile.empty:
        if (result.profile["n_comparisons"] < 5).any():
            raise ValueError("Driver DNA profile published below the five-race minimum")
        profile_metrics = [
            name for metric in METRICS for name in (metric, f"{metric}_lo", f"{metric}_hi")
        ]
        if not np.isfinite(result.profile[profile_metrics].to_numpy(dtype=float)).all():
            raise ValueError("Driver DNA profile contains non-finite estimates")
    if not result.microsectors.empty:
        micro_metrics = [
            "segment_delta_sec",
            "driver_speed_kph",
            "teammate_speed_kph",
            "driver_throttle",
            "teammate_throttle",
            "driver_brake_share",
            "teammate_brake_share",
            "x",
            "y",
        ]
        if not np.isfinite(result.microsectors[micro_metrics].to_numpy(dtype=float)).all():
            raise ValueError("Driver DNA microsectors contain non-finite values")


EVIDENCE_COLUMNS = [
    "season",
    "round",
    "race_name",
    "driver_code",
    "driver_name",
    "team",
    "teammate_code",
    "teammate_name",
    "driver_lap_number",
    "teammate_lap_number",
    "compound",
    "driver_tyre_life",
    "teammate_tyre_life",
    "driver_track_status",
    "teammate_track_status",
    "lap_number_gap",
    "tyre_life_gap",
    "pair_selection_score",
    "common_points",
    "valid_coverage_pct",
    "throttle_corrections",
    "gear_anomalies",
    "eligible",
    "exclusion_reason",
    *[name for metric in METRICS for name in (f"driver_{metric}", f"teammate_{metric}")],
    *[f"{metric}_delta" for metric in METRICS],
    *[f"{metric}_z" for metric in METRICS],
    "methodology_version",
]

PROFILE_COLUMNS = [
    "from_season",
    "to_season",
    "driver_code",
    "driver_name",
    "n_comparisons",
    "n_teammates",
    "n_seasons",
    "first_season",
    "last_season",
    "confidence",
    *[name for metric in METRICS for name in (metric, f"{metric}_lo", f"{metric}_hi")],
    "bootstrap_samples",
    "methodology_version",
]

MICROSECTOR_COLUMNS = [
    "season",
    "round",
    "race_name",
    "driver_code",
    "driver_name",
    "teammate_code",
    "teammate_name",
    "driver_lap_number",
    "teammate_lap_number",
    "compound",
    "segment_number",
    "start_distance_m",
    "end_distance_m",
    "segment_delta_sec",
    "driver_speed_kph",
    "teammate_speed_kph",
    "driver_throttle",
    "teammate_throttle",
    "driver_brake_share",
    "teammate_brake_share",
    "x",
    "y",
    "methodology_version",
]


def _empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    valid = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not valid.any():
        return float("nan")
    return float(np.average(values[valid], weights=weights[valid]))


def distance_weighted_share(
    distance_m: pd.Series | np.ndarray,
    condition: pd.Series | np.ndarray,
) -> float:
    """Return the share of lap distance for which ``condition`` is true.

    Each interval is represented by its end sample.  This is stable on both the
    regular 25 m production grid and irregular synthetic test grids.
    """
    distance = np.asarray(distance_m, dtype=float)
    active = np.asarray(condition, dtype=bool)
    if len(distance) < 2 or len(active) != len(distance):
        return float("nan")
    dx = np.diff(distance)
    valid = np.isfinite(dx) & (dx > 0)
    if not valid.any():
        return float("nan")
    return float(np.sum(dx[valid] * active[1:][valid]) / np.sum(dx[valid]))


def confirmed_brake_onsets(
    telemetry: pd.DataFrame,
    *,
    quiet_distance_m: float = 50.0,
    braking_distance_m: float = 50.0,
) -> pd.DataFrame:
    """Find brake transitions with 50 m of quiet and sustained braking either side."""
    frame = telemetry.sort_values("distance_m").reset_index(drop=True)
    if len(frame) < 3:
        return frame.iloc[0:0].copy()
    distance = frame["distance_m"].to_numpy(dtype=float)
    brake = frame["brake"].fillna(0).astype(bool).to_numpy()
    accepted: list[int] = []
    for index in np.flatnonzero(brake & ~np.r_[False, brake[:-1]]):
        onset = distance[index]
        before = (distance >= onset - quiet_distance_m) & (distance < onset)
        after = (distance >= onset) & (distance <= onset + braking_distance_m)
        before_reaches = bool(before.any() and distance[before].min() <= onset - quiet_distance_m)
        after_reaches = bool(after.any() and distance[after].max() >= onset + braking_distance_m)
        if before_reaches and after_reaches and not brake[before].any() and brake[after].all():
            accepted.append(int(index))
    return frame.iloc[accepted].reset_index(drop=True)


def clean_telemetry(telemetry: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float | int]]:
    """Clean physical channels while preserving auditable correction counts."""
    frame = telemetry.copy()
    for column in ("distance_m", "speed_kph", "throttle", "brake", "gear", "x", "y"):
        if column not in frame:
            frame[column] = np.nan
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    original_rows = len(frame)
    throttle_corrections = int(((frame["throttle"] < 0) | (frame["throttle"] > 100)).sum())
    frame["throttle"] = frame["throttle"].clip(0, 100)
    gear_anomalies = int((~frame["gear"].between(0, 9) & frame["gear"].notna()).sum())
    valid = (
        frame["distance_m"].notna()
        & frame["speed_kph"].notna()
        & frame["throttle"].notna()
        & frame["brake"].notna()
        & (frame["distance_m"] >= 0)
        & (frame["speed_kph"] > 0)
        & (frame["speed_kph"] <= 400)
        & frame["brake"].isin([0, 1])
    )
    frame = (
        frame.loc[valid]
        .sort_values("distance_m")
        .drop_duplicates("distance_m", keep="last")
        .reset_index(drop=True)
    )
    coverage = 100.0 * len(frame) / original_rows if original_rows else 0.0
    return frame, {
        "original_points": original_rows,
        "valid_points": len(frame),
        "valid_coverage_pct": coverage,
        "throttle_corrections": throttle_corrections,
        "gear_anomalies": gear_anomalies,
    }


def lap_metrics(
    telemetry: pd.DataFrame, reference_speed: pd.Series | np.ndarray
) -> dict[str, float]:
    """Calculate the five distance-weighted Driver DNA technique metrics."""
    distance = telemetry["distance_m"].to_numpy(dtype=float)
    speed = telemetry["speed_kph"].to_numpy(dtype=float)
    throttle = telemetry["throttle"].to_numpy(dtype=float)
    brake = telemetry["brake"].to_numpy(dtype=float)
    ref = np.asarray(reference_speed, dtype=float)
    if len(distance) < 2 or len(ref) != len(distance):
        return {metric: float("nan") for metric in METRICS}
    dx = np.r_[0.0, np.diff(distance)]
    low_speed = ref <= 160.0
    onsets = confirmed_brake_onsets(telemetry)
    return {
        "full_throttle_share": distance_weighted_share(distance, throttle >= 99.0),
        "coasting_share": distance_weighted_share(distance, (throttle <= 5.0) & (brake == 0)),
        "braking_share": distance_weighted_share(distance, brake == 1),
        "brake_onset_speed_kph": (
            float(onsets["speed_kph"].median()) if not onsets.empty else float("nan")
        ),
        "low_speed_kph": _weighted_mean(speed[low_speed], dx[low_speed]),
    }


def integrate_segment_time(distance_m: np.ndarray, speed_kph: np.ndarray) -> np.ndarray:
    """Trapezoidal interval times in seconds: ``7.2 * dx / (v_i + v_i-1)``."""
    distance = np.asarray(distance_m, dtype=float)
    speed = np.asarray(speed_kph, dtype=float)
    if len(distance) != len(speed):
        raise ValueError("distance and speed must have the same length")
    if len(distance) < 2:
        return np.array([], dtype=float)
    denominator = speed[1:] + speed[:-1]
    dx = np.diff(distance)
    result: np.ndarray = np.divide(
        7.2 * dx,
        denominator,
        out=np.full(len(dx), np.nan, dtype=float),
        where=(denominator > 0) & (dx > 0),
    )
    return result


def build_microsectors(
    driver: pd.DataFrame,
    teammate: pd.DataFrame,
    *,
    segment_length_m: float = MICROSECTOR_LENGTH_M,
) -> pd.DataFrame:
    """Build fixed-distance microsectors; positive delta means the driver gains."""
    paired = driver.merge(teammate, on="distance_m", suffixes=("_driver", "_teammate"))
    paired = paired.sort_values("distance_m").reset_index(drop=True)
    if len(paired) < 2:
        return pd.DataFrame()
    distance = paired["distance_m"].to_numpy(dtype=float)
    intervals = pd.DataFrame(
        {
            "start_distance_m": distance[:-1],
            "end_distance_m": distance[1:],
            "driver_time_sec": integrate_segment_time(
                distance, paired["speed_kph_driver"].to_numpy(dtype=float)
            ),
            "teammate_time_sec": integrate_segment_time(
                distance, paired["speed_kph_teammate"].to_numpy(dtype=float)
            ),
            "driver_speed_kph": paired["speed_kph_driver"].to_numpy(dtype=float)[1:],
            "teammate_speed_kph": paired["speed_kph_teammate"].to_numpy(dtype=float)[1:],
            "driver_throttle": paired["throttle_driver"].to_numpy(dtype=float)[1:],
            "teammate_throttle": paired["throttle_teammate"].to_numpy(dtype=float)[1:],
            "driver_brake_share": paired["brake_driver"].to_numpy(dtype=float)[1:],
            "teammate_brake_share": paired["brake_teammate"].to_numpy(dtype=float)[1:],
            "x": paired["x_driver"].to_numpy(dtype=float)[1:],
            "y": paired["y_driver"].to_numpy(dtype=float)[1:],
        }
    )
    intervals["segment_number"] = (
        np.floor(intervals["start_distance_m"] / segment_length_m).astype(int) + 1
    )
    intervals["weight"] = intervals["end_distance_m"] - intervals["start_distance_m"]

    rows: list[dict[str, float | int]] = []
    for number, group in intervals.groupby("segment_number", sort=True):
        weights = group["weight"].to_numpy(dtype=float)
        rows.append(
            {
                "segment_number": int(number),
                "start_distance_m": float(group["start_distance_m"].min()),
                "end_distance_m": float(group["end_distance_m"].max()),
                "segment_delta_sec": float(
                    (group["teammate_time_sec"] - group["driver_time_sec"]).sum()
                ),
                **{
                    column: _weighted_mean(group[column].to_numpy(dtype=float), weights)
                    for column in (
                        "driver_speed_kph",
                        "teammate_speed_kph",
                        "driver_throttle",
                        "teammate_throttle",
                        "driver_brake_share",
                        "teammate_brake_share",
                        "x",
                        "y",
                    )
                },
            }
        )
    return pd.DataFrame(rows)


def robust_standardize(evidence: pd.DataFrame) -> pd.DataFrame:
    """Add robust z deltas using one global MAD scale per technique metric."""
    result = evidence.copy()
    eligible = result["eligible"].fillna(False).astype(bool)
    for metric in METRICS:
        delta_column = f"{metric}_delta"
        z_column = f"{metric}_z"
        values = pd.to_numeric(result.loc[eligible, delta_column], errors="coerce")
        centre = float(values.median())
        mad = float((values - centre).abs().median())
        scale = 1.4826 * mad
        result[z_column] = np.nan
        if np.isfinite(scale) and scale > 0:
            result.loc[eligible, z_column] = (values - centre) / scale
        elif values.notna().any():
            result.loc[eligible, z_column] = 0.0
    return result


def bootstrap_profile(
    values: pd.DataFrame,
    *,
    n_boot: int = 1000,
    seed: int = 0,
) -> dict[str, tuple[float, float, float]]:
    """Race-cluster bootstrap medians with deterministic 90% intervals."""
    if values.empty:
        return {metric: (float("nan"), float("nan"), float("nan")) for metric in METRICS}
    if n_boot <= 0:
        return {
            metric: (float(values[f"{metric}_z"].median()), float("nan"), float("nan"))
            for metric in METRICS
        }
    race_values = values.groupby(["season", "round"], as_index=False)[
        [f"{metric}_z" for metric in METRICS]
    ].median()
    rng = np.random.default_rng(seed)
    chosen = rng.integers(0, len(race_values), size=(n_boot, len(race_values)))
    samples: dict[str, np.ndarray] = {
        metric: np.nanmedian(race_values[f"{metric}_z"].to_numpy(dtype=float)[chosen], axis=1)
        for metric in METRICS
    }
    return {
        metric: (
            float(values[f"{metric}_z"].median()),
            float(np.nanquantile(samples[metric], 0.05)),
            float(np.nanquantile(samples[metric], 0.95)),
        )
        for metric in METRICS
    }


def build_profiles(
    evidence: pd.DataFrame,
    *,
    n_boot: int = 1000,
    seed: int = 0,
    min_comparisons: int = 5,
) -> pd.DataFrame:
    """Aggregate eligible directed observations into publishable driver profiles."""
    eligible = evidence[evidence["eligible"].fillna(False)].copy()
    rows: list[dict[str, object]] = []
    for offset, (driver_code, group) in enumerate(eligible.groupby("driver_code", sort=True)):
        if len(group) < min_comparisons:
            continue
        estimates = bootstrap_profile(group, n_boot=n_boot, seed=seed + offset)
        count = len(group)
        confidence = "strong" if count >= 12 else "moderate" if count >= 8 else "limited"
        row: dict[str, object] = {
            "from_season": int(group["season"].min()),
            "to_season": int(group["season"].max()),
            "driver_code": driver_code,
            "driver_name": group["driver_name"].dropna().iloc[0],
            "n_comparisons": count,
            "n_teammates": int(group["teammate_code"].nunique()),
            "n_seasons": int(group["season"].nunique()),
            "first_season": int(group["season"].min()),
            "last_season": int(group["season"].max()),
            "confidence": confidence,
            "bootstrap_samples": n_boot,
            "methodology_version": METHODOLOGY_VERSION,
        }
        for metric, (estimate, low, high) in estimates.items():
            row[metric] = estimate
            row[f"{metric}_lo"] = low
            row[f"{metric}_hi"] = high
        rows.append(row)
    return pd.DataFrame(rows, columns=PROFILE_COLUMNS)


def build_profile_windows(
    evidence: pd.DataFrame,
    *,
    n_boot: int = 1000,
    seed: int = 0,
) -> pd.DataFrame:
    """Publish every contiguous season window so dashboard filters stay honest."""
    eligible = evidence[evidence["eligible"].fillna(False)]
    seasons = sorted(int(season) for season in eligible["season"].dropna().unique())
    frames: list[pd.DataFrame] = []
    window_offset = 0
    for start_index, from_season in enumerate(seasons):
        for to_season in seasons[start_index:]:
            scoped = evidence[evidence["season"].between(from_season, to_season)]
            profile = build_profiles(scoped, n_boot=n_boot, seed=seed + window_offset * 100)
            if not profile.empty:
                profile["from_season"] = from_season
                profile["to_season"] = to_season
                frames.append(profile)
            window_offset += 1
    return pd.concat(frames, ignore_index=True) if frames else _empty(PROFILE_COLUMNS)


def _candidate_laps(telemetry: pd.DataFrame, laps: pd.DataFrame) -> pd.DataFrame:
    available = telemetry[["season", "round", "driver_code", "lap_number"]].drop_duplicates()
    metadata = laps.copy()
    if "session" in metadata:
        metadata = metadata[metadata["session"] == "R"]
    joined = available.merge(
        metadata,
        on=["season", "round", "driver_code", "lap_number"],
        how="left",
        suffixes=("", "_lap"),
    )
    joined["lap_time_sec"] = pd.to_numeric(joined["lap_time_sec"], errors="coerce")
    return joined.sort_values(
        ["season", "round", "driver_code", "lap_time_sec", "lap_number"],
        na_position="last",
    ).drop_duplicates(["season", "round", "driver_code", "lap_number"], keep="first")


def _exclusion_reason(
    a: pd.Series,
    b: pd.Series,
    *,
    max_lap_gap: int = DEFAULT_MAX_LAP_GAP,
    max_tyre_life_gap: int = DEFAULT_MAX_TYRE_LIFE_GAP,
) -> str | None:
    if pd.isna(a.get("compound")) or pd.isna(b.get("compound")):
        return "missing compound"
    compound_a = str(a.get("compound", "")).upper()
    compound_b = str(b.get("compound", "")).upper()
    if not compound_a or compound_a == "NAN" or not compound_b or compound_b == "NAN":
        return "missing compound"
    if compound_a not in DRY_COMPOUNDS or compound_b not in DRY_COMPOUNDS:
        return "non-dry compound"
    if compound_a != compound_b:
        return "different compound"
    if str(a.get("track_status", "")) != "1" or str(b.get("track_status", "")) != "1":
        return "non-green track status"
    tyre_a = pd.to_numeric(a.get("tyre_life"), errors="coerce")
    tyre_b = pd.to_numeric(b.get("tyre_life"), errors="coerce")
    if pd.isna(tyre_a) or pd.isna(tyre_b):
        return "missing tyre life"
    if abs(float(a["lap_number"]) - float(b["lap_number"])) > max_lap_gap:
        return f"lap-number gap above {max_lap_gap}"
    if abs(float(tyre_a) - float(tyre_b)) > max_tyre_life_gap:
        return f"tyre-life gap above {max_tyre_life_gap}"
    return None


def select_representative_pair(
    driver_laps: pd.DataFrame,
    teammate_laps: pd.DataFrame,
    *,
    max_lap_gap: int = DEFAULT_MAX_LAP_GAP,
    max_tyre_life_gap: int = DEFAULT_MAX_TYRE_LIFE_GAP,
) -> tuple[pd.Series, pd.Series, float]:
    """Select the fastest jointly comparable teammate lap pair."""
    if driver_laps.empty or teammate_laps.empty:
        raise ValueError("both drivers need at least one telemetry-backed lap")
    fastest_a = pd.to_numeric(driver_laps["lap_time_sec"], errors="coerce").min()
    fastest_b = pd.to_numeric(teammate_laps["lap_time_sec"], errors="coerce").min()
    candidates: list[tuple[tuple[float, ...], pd.Series, pd.Series, float]] = []
    for _, a in driver_laps.iterrows():
        for _, b in teammate_laps.iterrows():
            lap_gap = abs(float(a["lap_number"]) - float(b["lap_number"]))
            tyre_a = pd.to_numeric(a.get("tyre_life"), errors="coerce")
            tyre_b = pd.to_numeric(b.get("tyre_life"), errors="coerce")
            tyre_gap = (
                abs(float(tyre_a) - float(tyre_b))
                if pd.notna(tyre_a) and pd.notna(tyre_b)
                else float("inf")
            )
            time_a = pd.to_numeric(a.get("lap_time_sec"), errors="coerce")
            time_b = pd.to_numeric(b.get("lap_time_sec"), errors="coerce")
            deficit_a = float(time_a - fastest_a) if pd.notna(time_a) else 1_000.0
            deficit_b = float(time_b - fastest_b) if pd.notna(time_b) else 1_000.0
            score = deficit_a + deficit_b + 0.03 * lap_gap + 0.03 * tyre_gap
            reason = _exclusion_reason(
                a,
                b,
                max_lap_gap=max_lap_gap,
                max_tyre_life_gap=max_tyre_life_gap,
            )
            sort_key = (float(reason is not None), score, lap_gap, tyre_gap)
            candidates.append((sort_key, a, b, score))
    _, selected_a, selected_b, score = min(candidates, key=lambda candidate: candidate[0])
    return selected_a, selected_b, float(score)


def analyse_driver_dna(
    telemetry: pd.DataFrame,
    laps: pd.DataFrame,
    *,
    n_boot: int = 1000,
    seed: int = 0,
    max_lap_gap: int = DEFAULT_MAX_LAP_GAP,
    max_tyre_life_gap: int = DEFAULT_MAX_TYRE_LIFE_GAP,
) -> DriverDNAResult:
    """Build evidence, profile and microsector frames from telemetry-backed laps."""
    if telemetry.empty or laps.empty:
        return DriverDNAResult(
            _empty(EVIDENCE_COLUMNS), _empty(PROFILE_COLUMNS), _empty(MICROSECTOR_COLUMNS)
        )
    candidates = _candidate_laps(telemetry, laps)
    evidence_rows: list[dict[str, object]] = []
    microsector_frames: list[pd.DataFrame] = []
    group_columns = ["season", "round", "team"]
    for (season, rnd, team), team_laps in candidates.groupby(
        group_columns, dropna=False, sort=True
    ):
        driver_codes = sorted(str(code) for code in team_laps["driver_code"].dropna().unique())
        if pd.isna(team) or len(driver_codes) < 2:
            continue
        for code_a, code_b in combinations(driver_codes, 2):
            a, b, pair_score = select_representative_pair(
                team_laps[team_laps["driver_code"].astype(str) == code_a],
                team_laps[team_laps["driver_code"].astype(str) == code_b],
                max_lap_gap=max_lap_gap,
                max_tyre_life_gap=max_tyre_life_gap,
            )
            raw_a = telemetry[
                (telemetry["season"] == season)
                & (telemetry["round"] == rnd)
                & (telemetry["driver_code"] == code_a)
                & (telemetry["lap_number"] == a["lap_number"])
            ]
            raw_b = telemetry[
                (telemetry["season"] == season)
                & (telemetry["round"] == rnd)
                & (telemetry["driver_code"] == code_b)
                & (telemetry["lap_number"] == b["lap_number"])
            ]
            clean_a, audit_a = clean_telemetry(raw_a)
            clean_b, audit_b = clean_telemetry(raw_b)
            paired = clean_a.merge(clean_b, on="distance_m", suffixes=("_a", "_b"))
            common_points = len(paired)
            common_coverage = 100.0 * common_points / max(1, min(len(clean_a), len(clean_b)))
            valid_coverage = min(
                float(audit_a["valid_coverage_pct"]),
                float(audit_b["valid_coverage_pct"]),
                common_coverage,
            )
            reason = _exclusion_reason(
                a,
                b,
                max_lap_gap=max_lap_gap,
                max_tyre_life_gap=max_tyre_life_gap,
            )
            if reason is None and common_points < MIN_COMMON_POINTS:
                reason = "fewer than 100 common telemetry points"
            if reason is None and valid_coverage < MIN_VALID_COVERAGE_PCT:
                reason = "valid telemetry coverage below 95%"
            eligible = reason is None

            metrics_a = {metric: float("nan") for metric in METRICS}
            metrics_b = {metric: float("nan") for metric in METRICS}
            micro_ab = pd.DataFrame()
            if eligible:
                common_a = paired[
                    [
                        "distance_m",
                        "speed_kph_a",
                        "throttle_a",
                        "brake_a",
                        "gear_a",
                        "x_a",
                        "y_a",
                    ]
                ].rename(columns=lambda name: name.removesuffix("_a"))
                common_b = paired[
                    [
                        "distance_m",
                        "speed_kph_b",
                        "throttle_b",
                        "brake_b",
                        "gear_b",
                        "x_b",
                        "y_b",
                    ]
                ].rename(columns=lambda name: name.removesuffix("_b"))
                reference_speed = (
                    common_a["speed_kph"].to_numpy(dtype=float)
                    + common_b["speed_kph"].to_numpy(dtype=float)
                ) / 2.0
                metrics_a = lap_metrics(common_a, reference_speed)
                metrics_b = lap_metrics(common_b, reference_speed)
                micro_ab = build_microsectors(common_a, common_b)

            common = {
                "season": int(season),
                "round": int(rnd),
                "race_name": a.get("race_name", b.get("race_name")),
                "team": team,
                "compound": str(a.get("compound", "")).upper(),
                "lap_number_gap": abs(int(a["lap_number"]) - int(b["lap_number"])),
                "tyre_life_gap": (
                    abs(float(a["tyre_life"]) - float(b["tyre_life"]))
                    if pd.notna(a.get("tyre_life")) and pd.notna(b.get("tyre_life"))
                    else float("nan")
                ),
                "pair_selection_score": pair_score,
                "common_points": common_points,
                "valid_coverage_pct": valid_coverage,
                "throttle_corrections": int(audit_a["throttle_corrections"])
                + int(audit_b["throttle_corrections"]),
                "gear_anomalies": int(audit_a["gear_anomalies"]) + int(audit_b["gear_anomalies"]),
                "eligible": eligible,
                "exclusion_reason": reason,
                "methodology_version": METHODOLOGY_VERSION,
            }
            directions = ((a, b, metrics_a, metrics_b, 1), (b, a, metrics_b, metrics_a, -1))
            for driver_row, teammate_row, own, other, direction in directions:
                row = {
                    **common,
                    "driver_code": driver_row["driver_code"],
                    "driver_name": driver_row.get("driver_name", driver_row["driver_code"]),
                    "teammate_code": teammate_row["driver_code"],
                    "teammate_name": teammate_row.get("driver_name", teammate_row["driver_code"]),
                    "driver_lap_number": int(driver_row["lap_number"]),
                    "teammate_lap_number": int(teammate_row["lap_number"]),
                    "driver_tyre_life": driver_row.get("tyre_life"),
                    "teammate_tyre_life": teammate_row.get("tyre_life"),
                    "driver_track_status": driver_row.get("track_status"),
                    "teammate_track_status": teammate_row.get("track_status"),
                }
                for metric in METRICS:
                    row[f"driver_{metric}"] = own[metric]
                    row[f"teammate_{metric}"] = other[metric]
                    row[f"{metric}_delta"] = (
                        own[metric] - other[metric] if eligible else float("nan")
                    )
                evidence_rows.append(row)

                if eligible and not micro_ab.empty:
                    micro = micro_ab.copy()
                    if direction < 0:
                        micro["segment_delta_sec"] *= -1
                        for left, right in (
                            ("driver_speed_kph", "teammate_speed_kph"),
                            ("driver_throttle", "teammate_throttle"),
                            ("driver_brake_share", "teammate_brake_share"),
                        ):
                            micro[[left, right]] = micro[[right, left]].to_numpy()
                    micro = micro.assign(
                        season=int(season),
                        round=int(rnd),
                        race_name=common["race_name"],
                        driver_code=driver_row["driver_code"],
                        driver_name=driver_row.get("driver_name", driver_row["driver_code"]),
                        teammate_code=teammate_row["driver_code"],
                        teammate_name=teammate_row.get("driver_name", teammate_row["driver_code"]),
                        driver_lap_number=int(driver_row["lap_number"]),
                        teammate_lap_number=int(teammate_row["lap_number"]),
                        compound=common["compound"],
                        methodology_version=METHODOLOGY_VERSION,
                    )
                    microsector_frames.append(micro[MICROSECTOR_COLUMNS])

    evidence = pd.DataFrame(evidence_rows)
    if evidence.empty:
        evidence = _empty(EVIDENCE_COLUMNS)
    else:
        evidence = robust_standardize(evidence)
        evidence = evidence[EVIDENCE_COLUMNS].sort_values(
            ["season", "round", "team", "driver_code", "teammate_code"]
        )
    profile = build_profile_windows(evidence, n_boot=n_boot, seed=seed)
    microsectors = (
        pd.concat(microsector_frames, ignore_index=True)
        if microsector_frames
        else _empty(MICROSECTOR_COLUMNS)
    )
    return DriverDNAResult(
        evidence.reset_index(drop=True),
        profile.reset_index(drop=True),
        microsectors.reset_index(drop=True),
    )
