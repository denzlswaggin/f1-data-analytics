"""Counterfactual sensitivity of a driver's observed pit-stop timing.

The model asks a deliberately narrow question: given the clean-air pace that
was observed immediately around a stop, would moving the same stop a few laps
have reduced the modelled race-time cost?  It is not a strategy optimiser and
does not infer unobserved traffic, safety cars, tyre availability, or pit loss.
Those limitations are made visible through eligibility and uncertainty fields.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
import pandas as pd

from analytics.pit_context import attach_pit_lap_context, build_pit_lap_context
from analytics.traffic import classify_representative_lap_air

METHODOLOGY_VERSION = "pit-timing-sensitivity-v3"
SUPPORTED_COMPOUNDS = {"SOFT", "MEDIUM", "HARD"}
SCENARIO_SHIFTS = tuple(range(-3, 4))
MIN_FIELD_PEERS = 5
MIN_REPLAY_COVERAGE_PCT = 80.0
MIN_OLD_REFERENCE_LAPS = 4
MAX_OLD_REFERENCE_LAPS = 6
MIN_NEW_MATURE_LAPS = 3
MAX_MODEL_MAD_SEC = 0.50
MEANINGFUL_GAIN_SEC = 0.30
BOOTSTRAP_SAMPLES = 300
MIN_BOOTSTRAP_VALID_SAMPLES = 100
MIN_BOOTSTRAP_COMPLETION = 0.90
MAX_OLD_EXTRAPOLATION_LAPS = 4.0
MAX_NEW_EXTRAPOLATION_LAPS = 3.0

_DRIVER_KEYS = ["season", "round", "driver_code"]
_LAP_KEYS = [*_DRIVER_KEYS, "lap_number"]
_LAP_REQUIRED = {
    *_LAP_KEYS,
    "race_name",
    "driver_name",
    "team",
    "stint",
    "compound",
    "tyre_life",
    "is_fresh_tyre",
    "lap_time_sec",
    "track_status",
}
_REPLAY_REQUIRED = {
    *_LAP_KEYS,
    "t_s",
    "running_order",
    "gap_to_ahead_s",
    "stint",
}
_STOP_REQUIRED = {*_DRIVER_KEYS, "pit_lap", "duration_sec"}

PIT_TIMING_COLUMNS = [
    "season",
    "round",
    "race_name",
    "driver_code",
    "driver_name",
    "team",
    "stop_number",
    "actual_pit_lap",
    "actual_out_lap",
    "pit_duration_sec",
    "official_pit_match",
    "old_stint",
    "new_stint",
    "old_compound",
    "new_compound",
    "new_tyre_fresh",
    "window_start_lap",
    "window_end_lap",
    "best_supported_shift_laps",
    "best_hypothetical_pit_lap",
    "estimated_gain_vs_actual_sec",
    "best_delta_p25_sec",
    "best_delta_p75_sec",
    "best_shift_win_pct",
    "best_earlier_delta_sec",
    "best_later_delta_sec",
    "supported_scenarios",
    "bootstrap_requested_samples",
    "bootstrap_valid_samples",
    "bootstrap_attempted_samples",
    "boundary_minimum",
    "best_old_extrapolation_laps",
    "best_new_extrapolation_laps",
    "actual_old_extrapolation_laps",
    "actual_new_extrapolation_laps",
    "old_reference_laps",
    "new_mature_reference_laps",
    "warmup_profile_laps",
    "old_slope_sec_per_tyre_lap",
    "new_slope_sec_per_stint_lap",
    "old_model_mad_sec",
    "new_model_mad_sec",
    "replay_coverage_pct",
    "field_peer_count_median",
    "timing_signal",
    "eligible",
    "exclusion_reason",
    "confidence",
    "methodology_version",
]

PIT_TIMING_SCENARIO_COLUMNS = [
    "season",
    "round",
    "race_name",
    "driver_code",
    "driver_name",
    "team",
    "stop_number",
    "actual_pit_lap",
    "actual_out_lap",
    "shift_laps",
    "hypothetical_pit_lap",
    "hypothetical_out_lap",
    "estimated_cost_index_sec",
    "delta_vs_actual_sec",
    "estimated_gain_vs_actual_sec",
    "delta_p25_sec",
    "delta_p75_sec",
    "old_tyre_extension_laps",
    "old_extrapolation_laps",
    "new_extrapolation_laps",
    "supported",
    "exclusion_reason",
    "methodology_version",
]

_SUMMARY_INTEGER = {
    "season",
    "round",
    "stop_number",
    "actual_pit_lap",
    "actual_out_lap",
    "old_stint",
    "new_stint",
    "window_start_lap",
    "window_end_lap",
    "best_supported_shift_laps",
    "best_hypothetical_pit_lap",
    "supported_scenarios",
    "bootstrap_requested_samples",
    "bootstrap_valid_samples",
    "bootstrap_attempted_samples",
    "old_reference_laps",
    "new_mature_reference_laps",
    "warmup_profile_laps",
}
_SUMMARY_FLOAT = {
    "best_old_extrapolation_laps",
    "best_new_extrapolation_laps",
    "actual_old_extrapolation_laps",
    "actual_new_extrapolation_laps",
    "pit_duration_sec",
    "estimated_gain_vs_actual_sec",
    "best_delta_p25_sec",
    "best_delta_p75_sec",
    "best_shift_win_pct",
    "best_earlier_delta_sec",
    "best_later_delta_sec",
    "old_slope_sec_per_tyre_lap",
    "new_slope_sec_per_stint_lap",
    "old_model_mad_sec",
    "new_model_mad_sec",
    "replay_coverage_pct",
    "field_peer_count_median",
}
_SUMMARY_BOOLEAN = {"official_pit_match", "new_tyre_fresh", "eligible", "boundary_minimum"}
_SCENARIO_INTEGER = {
    "season",
    "round",
    "stop_number",
    "actual_pit_lap",
    "actual_out_lap",
    "shift_laps",
    "hypothetical_pit_lap",
    "hypothetical_out_lap",
    "old_tyre_extension_laps",
}
_SCENARIO_FLOAT = {
    "old_extrapolation_laps",
    "new_extrapolation_laps",
    "estimated_cost_index_sec",
    "delta_vs_actual_sec",
    "estimated_gain_vs_actual_sec",
    "delta_p25_sec",
    "delta_p75_sec",
}
_SCENARIO_BOOLEAN = {"supported"}


@dataclass(frozen=True)
class PitTimingSensitivityResult:
    """Stop-level conclusions and the seven scenario rows behind each one."""

    summary: pd.DataFrame
    scenarios: pd.DataFrame


@dataclass(frozen=True)
class _StopModel:
    old_slope: float
    old_intercept: float
    new_slope: float
    new_intercept: float
    old_mad: float
    new_mad: float
    actual_in_age: float
    warmup: dict[int, float]


@dataclass(frozen=True)
class _BootstrapResult:
    deltas: dict[int, np.ndarray]
    requested: int
    attempted: int

    @property
    def valid(self) -> int:
        return len(self.deltas[0])


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


def _empty_result() -> PitTimingSensitivityResult:
    return PitTimingSensitivityResult(
        summary=_typed_empty(
            PIT_TIMING_COLUMNS, _SUMMARY_INTEGER, _SUMMARY_FLOAT, _SUMMARY_BOOLEAN
        ),
        scenarios=_typed_empty(
            PIT_TIMING_SCENARIO_COLUMNS,
            _SCENARIO_INTEGER,
            _SCENARIO_FLOAT,
            _SCENARIO_BOOLEAN,
        ),
    )


def _require_columns(frame: pd.DataFrame, required: set[str], name: str) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{name} is missing columns: {sorted(missing)}")


def _theil_sen(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    slopes: list[float] = []
    for left in range(len(x) - 1):
        delta_x = x[left + 1 :] - x[left]
        usable = delta_x != 0
        if usable.any():
            slopes.extend(((y[left + 1 :] - y[left])[usable] / delta_x[usable]).tolist())
    if not slopes:
        raise ValueError("model needs at least two distinct x values")
    slope = float(np.median(slopes))
    intercept = float(np.median(y - slope * x))
    return slope, intercept


def _fit(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    slope, intercept = _theil_sen(x, y)
    residual = y - (intercept + slope * x)
    centre = float(np.median(residual))
    intercept += centre
    mad = float(np.median(np.abs(y - (intercept + slope * x))))
    return slope, intercept, mad


def _prepare_laps(laps: pd.DataFrame) -> pd.DataFrame:
    out = laps.copy()
    numeric = ["season", "round", "lap_number", "stint", "tyre_life", "lap_time_sec"]
    for column in numeric:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out[numeric] = out[numeric].replace([np.inf, -np.inf], np.nan)
    out = out.dropna(subset=[*_LAP_KEYS, "stint"])
    duplicate = out.duplicated(subset=_LAP_KEYS, keep=False)
    if duplicate.any():
        raise ValueError("laps contains duplicate driver-lap rows")
    out["compound"] = out["compound"].astype("string").str.strip().str.upper()
    out["track_status"] = out["track_status"].astype("string").str.strip()
    return out.sort_values([*_DRIVER_KEYS, "lap_number"]).reset_index(drop=True)


def _derive_transitions(laps: pd.DataFrame) -> pd.DataFrame:
    out = laps.copy()
    grouped = out.groupby(_DRIVER_KEYS, sort=False, dropna=False)
    out["previous_lap"] = grouped["lap_number"].shift()
    out["previous_stint"] = grouped["stint"].shift()
    out["previous_compound"] = grouped["compound"].shift()
    contiguous = out["lap_number"].eq(out["previous_lap"] + 1)
    changed = out["stint"].gt(out["previous_stint"])
    transitions = out.loc[contiguous & changed].copy()
    transitions["stop_number"] = transitions.groupby(_DRIVER_KEYS).cumcount() + 1
    transitions["actual_out_lap"] = transitions["lap_number"]
    transitions["actual_pit_lap"] = transitions["lap_number"] - 1
    transitions["old_stint"] = transitions["previous_stint"]
    transitions["new_stint"] = transitions["stint"]
    transitions["old_compound"] = transitions["previous_compound"]
    transitions["new_compound"] = transitions["compound"]
    transitions["new_tyre_fresh"] = transitions["is_fresh_tyre"].fillna(False).astype(bool)
    columns = [
        *_DRIVER_KEYS,
        "race_name",
        "driver_name",
        "team",
        "stop_number",
        "actual_pit_lap",
        "actual_out_lap",
        "old_stint",
        "new_stint",
        "old_compound",
        "new_compound",
        "new_tyre_fresh",
    ]
    return transitions.loc[:, columns].reset_index(drop=True)


def _prepare_stops(stops: pd.DataFrame | None) -> pd.DataFrame:
    columns = [*_DRIVER_KEYS, "pit_lap", "duration_sec"]
    if stops is None or stops.empty:
        return pd.DataFrame(columns=columns)
    _require_columns(stops, _STOP_REQUIRED, "stops")
    out = stops.loc[:, columns].copy()
    for column in ("season", "round", "pit_lap", "duration_sec"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out = out.dropna(subset=[*_DRIVER_KEYS, "pit_lap"])
    out = out.sort_values([*_DRIVER_KEYS, "pit_lap", "duration_sec"]).drop_duplicates(
        [*_DRIVER_KEYS, "pit_lap"], keep="first"
    )
    return out


def _attach_stop_context(transitions: pd.DataFrame, stops: pd.DataFrame | None) -> pd.DataFrame:
    official = _prepare_stops(stops).rename(columns={"pit_lap": "actual_pit_lap"})
    out = transitions.merge(
        official,
        on=[*_DRIVER_KEYS, "actual_pit_lap"],
        how="left",
        validate="many_to_one",
    )
    out["pit_duration_sec"] = out.pop("duration_sec")
    out["official_pit_match"] = out["pit_duration_sec"].notna()
    return out


def _add_field_residuals(
    laps: pd.DataFrame,
    replay: pd.DataFrame,
    *,
    min_field_peers: int,
    min_replay_coverage_pct: float,
) -> pd.DataFrame:
    green = laps.loc[laps["track_status"].eq("1")].copy()
    context = classify_representative_lap_air(
        green, replay, min_replay_coverage=min_replay_coverage_pct / 100.0
    )
    if context.empty:
        return context.assign(
            field_peer_count=pd.Series(dtype="Int64"),
            field_peer_median_sec=pd.Series(dtype="float64"),
            field_pace_residual_sec=pd.Series(dtype="float64"),
        )
    context["field_peer_count"] = 0
    context["field_peer_median_sec"] = np.nan
    clean = context.loc[
        context["air_state"].eq("clean_air")
        & context["replay_coverage_pct"].ge(min_replay_coverage_pct)
    ]
    for _, group in clean.groupby(["season", "round", "lap_number"], sort=False):
        for index, _row in group.iterrows():
            peers = group.loc[group.index != index, "lap_time_sec"].dropna()
            context.loc[index, "field_peer_count"] = len(peers)
            if len(peers) >= min_field_peers:
                context.loc[index, "field_peer_median_sec"] = float(peers.median())
    context["field_pace_residual_sec"] = context["lap_time_sec"] - context["field_peer_median_sec"]
    return context


def _base_exclusion(
    transition: pd.Series,
    driver_laps: pd.DataFrame,
    all_transitions: pd.DataFrame,
) -> str:
    old_compound = str(transition["old_compound"])
    new_compound = str(transition["new_compound"])
    if old_compound not in SUPPORTED_COMPOUNDS or new_compound not in SUPPORTED_COMPOUNDS:
        return "unsupported_compound"
    out_lap = int(transition["actual_out_lap"])
    start, end = out_lap - 3, out_lap + 9
    window = driver_laps.loc[driver_laps["lap_number"].between(start, end)]
    if set(window["lap_number"].astype(int)) != set(range(start, end + 1)):
        return "incomplete_evaluation_window"
    if not window["track_status"].eq("1").all():
        return "non_green_evaluation_window"
    extra_pit = (window["is_pit_in_lap"].fillna(False) & window["lap_number"].ne(out_lap - 1)) | (
        window["is_pit_out_lap"].fillna(False) & window["lap_number"].ne(out_lap)
    )
    extra_pit |= window["is_pit_boundary"].fillna(False) & ~window["lap_number"].isin(
        [out_lap - 1, out_lap]
    )
    if extra_pit.any():
        return "additional_stop_in_window"
    other = all_transitions.loc[
        all_transitions["driver_code"].eq(transition["driver_code"])
        & all_transitions["actual_out_lap"].between(start, end)
        & all_transitions["actual_out_lap"].ne(out_lap)
    ]
    if not other.empty:
        return "additional_stop_in_window"
    return ""


def _build_model(
    transition: pd.Series,
    driver_laps: pd.DataFrame,
    residuals: pd.DataFrame,
) -> tuple[_StopModel | None, str, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    out_lap = int(transition["actual_out_lap"])
    old_stint = float(transition["old_stint"])
    new_stint = float(transition["new_stint"])
    driver_residuals = residuals.loc[
        residuals["driver_code"].eq(transition["driver_code"])
        & residuals["season"].eq(transition["season"])
        & residuals["round"].eq(transition["round"])
    ].copy()
    old = driver_residuals.loc[
        driver_residuals["stint"].eq(old_stint)
        & driver_residuals["lap_number"].lt(out_lap - 1)
        & driver_residuals["field_pace_residual_sec"].notna()
    ].nlargest(MAX_OLD_REFERENCE_LAPS, "lap_number")
    if len(old) < MIN_OLD_REFERENCE_LAPS:
        return None, "insufficient_old_reference_laps", old, old.iloc[0:0], old.iloc[0:0]

    new = driver_residuals.loc[
        driver_residuals["stint"].eq(new_stint)
        & driver_residuals["field_pace_residual_sec"].notna()
    ].copy()
    new["post_stop_offset"] = new["lap_number"] - out_lap
    warmup = new.loc[new["post_stop_offset"].between(1, 6)]
    if set(warmup["post_stop_offset"].astype(int)) != set(range(1, 7)):
        return None, "incomplete_warmup_profile", old, new.iloc[0:0], warmup
    mature = new.loc[new["post_stop_offset"].between(7, 12)]
    if len(mature) < MIN_NEW_MATURE_LAPS:
        return None, "insufficient_new_mature_laps", old, mature, warmup

    in_lap = driver_laps.loc[driver_laps["lap_number"].eq(out_lap - 1)]
    if in_lap.empty or pd.isna(in_lap.iloc[0]["tyre_life"]):
        return None, "missing_old_tyre_age", old, mature, warmup
    try:
        old_slope, old_intercept, old_mad = _fit(
            old["tyre_life"].to_numpy(dtype=float),
            old["field_pace_residual_sec"].to_numpy(dtype=float),
        )
        new_slope, new_intercept, new_mad = _fit(
            mature["post_stop_offset"].to_numpy(dtype=float),
            mature["field_pace_residual_sec"].to_numpy(dtype=float),
        )
    except ValueError:
        return None, "insufficient_model_variation", old, mature, warmup
    if old_mad > MAX_MODEL_MAD_SEC:
        return None, "noisy_old_stint_model", old, mature, warmup
    if new_mad > MAX_MODEL_MAD_SEC:
        return None, "noisy_new_stint_model", old, mature, warmup
    warmup_profile = {
        int(row.post_stop_offset): float(
            row.field_pace_residual_sec - (new_intercept + new_slope * float(row.post_stop_offset))
        )
        for row in warmup.itertuples()
    }
    model = _StopModel(
        old_slope=old_slope,
        old_intercept=old_intercept,
        new_slope=new_slope,
        new_intercept=new_intercept,
        old_mad=old_mad,
        new_mad=new_mad,
        actual_in_age=float(in_lap.iloc[0]["tyre_life"]),
        warmup=warmup_profile,
    )
    return model, "", old, mature, warmup


def _scenario_cost(model: _StopModel, actual_out_lap: int, shift: int) -> float:
    hypothetical_out = actual_out_lap + shift
    cost = 0.0
    for lap in range(actual_out_lap - 3, actual_out_lap + 10):
        if lap < hypothetical_out:
            tyre_age = model.actual_in_age + lap - (actual_out_lap - 1)
            cost += model.old_intercept + model.old_slope * tyre_age
        elif lap > hypothetical_out:
            offset = lap - hypothetical_out
            cost += model.new_intercept + model.new_slope * offset
            cost += model.warmup.get(offset, 0.0)
        # The single pit/out-lap transition term is held constant and cancels.
    return cost


def _bootstrap_deltas(
    old: pd.DataFrame,
    mature: pd.DataFrame,
    warmup: pd.DataFrame,
    *,
    actual_in_age: float,
    actual_out_lap: int,
    samples: int,
    seed: int,
) -> _BootstrapResult:
    rng = np.random.default_rng(seed)
    output: dict[int, list[float]] = {shift: [] for shift in SCENARIO_SHIFTS}
    attempts = 0
    while len(output[0]) < samples and attempts < samples * 10:
        attempts += 1
        old_sample = old.iloc[rng.integers(0, len(old), len(old))]
        new_sample = mature.iloc[rng.integers(0, len(mature), len(mature))]
        try:
            old_slope, old_intercept, old_mad = _fit(
                old_sample["tyre_life"].to_numpy(dtype=float),
                old_sample["field_pace_residual_sec"].to_numpy(dtype=float),
            )
            new_slope, new_intercept, new_mad = _fit(
                new_sample["post_stop_offset"].to_numpy(dtype=float),
                new_sample["field_pace_residual_sec"].to_numpy(dtype=float),
            )
        except ValueError:
            continue
        if not np.isfinite(
            [old_slope, old_intercept, old_mad, new_slope, new_intercept, new_mad]
        ).all():
            continue
        profile = {
            int(row.post_stop_offset): float(
                row.field_pace_residual_sec
                - (new_intercept + new_slope * float(row.post_stop_offset))
            )
            for row in warmup.itertuples()
        }
        sampled = _StopModel(
            old_slope,
            old_intercept,
            new_slope,
            new_intercept,
            old_mad,
            new_mad,
            actual_in_age,
            profile,
        )
        costs = {shift: _scenario_cost(sampled, actual_out_lap, shift) for shift in SCENARIO_SHIFTS}
        deltas = {shift: costs[shift] - costs[0] for shift in SCENARIO_SHIFTS}
        if not np.isfinite([*costs.values(), *deltas.values()]).all():
            continue
        for shift in SCENARIO_SHIFTS:
            output[shift].append(deltas[shift])
    return _BootstrapResult(
        {shift: np.asarray(values, dtype=float) for shift, values in output.items()},
        samples,
        attempts,
    )


def _tied_minima(costs: dict[int, float]) -> list[int]:
    minimum = min(costs.values())
    return [
        shift for shift in sorted(costs) if np.isclose(costs[shift], minimum, atol=1e-9, rtol=0)
    ]


def _best_shift(costs: dict[int, float]) -> int:
    return min(_tied_minima(costs), key=lambda shift: (shift != 0, abs(shift), shift))


def _extrapolation_distances(
    model: _StopModel, old: pd.DataFrame, mature: pd.DataFrame, out_lap: int, shift: int
) -> tuple[float, float]:
    old_ages = [
        model.actual_in_age + lap - (out_lap - 1)
        for lap in range(out_lap - 3, out_lap + 10)
        if lap < out_lap + shift
    ]
    # Offsets 1..6 reproduce observed warmup residuals exactly; they are not
    # extrapolated mature predictions despite the algebraic fit/profile split.
    new_offsets = [
        lap - (out_lap + shift)
        for lap in range(out_lap - 3, out_lap + 10)
        if lap - (out_lap + shift) >= 7
    ]

    def distance(values: list[float] | list[int], lower: float, upper: float) -> float:
        return max((max(lower - value, value - upper, 0.0) for value in values), default=0.0)

    return (
        distance(old_ages, float(old.tyre_life.min()), float(old.tyre_life.max())),
        distance(
            new_offsets,
            float(mature.post_stop_offset.min()),
            float(mature.post_stop_offset.max()),
        ),
    )


def _unsupported_scenarios(transition: pd.Series, reason: str) -> list[dict[str, object]]:
    return [
        {
            "season": transition["season"],
            "round": transition["round"],
            "race_name": transition["race_name"],
            "driver_code": transition["driver_code"],
            "driver_name": transition["driver_name"],
            "team": transition["team"],
            "stop_number": transition["stop_number"],
            "actual_pit_lap": transition["actual_pit_lap"],
            "actual_out_lap": transition["actual_out_lap"],
            "shift_laps": shift,
            "hypothetical_pit_lap": int(transition["actual_pit_lap"]) + shift,
            "hypothetical_out_lap": int(transition["actual_out_lap"]) + shift,
            "estimated_cost_index_sec": np.nan,
            "delta_vs_actual_sec": np.nan,
            "estimated_gain_vs_actual_sec": np.nan,
            "delta_p25_sec": np.nan,
            "delta_p75_sec": np.nan,
            "old_tyre_extension_laps": max(shift, 0),
            "old_extrapolation_laps": np.nan,
            "new_extrapolation_laps": np.nan,
            "supported": False,
            "exclusion_reason": reason,
            "methodology_version": METHODOLOGY_VERSION,
        }
        for shift in SCENARIO_SHIFTS
    ]


def _summary_base(transition: pd.Series) -> dict[str, object]:
    return {
        "season": transition["season"],
        "round": transition["round"],
        "race_name": transition["race_name"],
        "driver_code": transition["driver_code"],
        "driver_name": transition["driver_name"],
        "team": transition["team"],
        "stop_number": transition["stop_number"],
        "actual_pit_lap": transition["actual_pit_lap"],
        "actual_out_lap": transition["actual_out_lap"],
        "pit_duration_sec": transition["pit_duration_sec"],
        "official_pit_match": transition["official_pit_match"],
        "old_stint": transition["old_stint"],
        "new_stint": transition["new_stint"],
        "old_compound": transition["old_compound"],
        "new_compound": transition["new_compound"],
        "new_tyre_fresh": transition["new_tyre_fresh"],
        "window_start_lap": int(transition["actual_out_lap"]) - 3,
        "window_end_lap": int(transition["actual_out_lap"]) + 9,
    }


def _excluded_summary(
    transition: pd.Series,
    reason: str,
    old_count: int = 0,
    mature_count: int = 0,
    warmup_count: int = 0,
) -> dict[str, object]:
    return {
        **_summary_base(transition),
        "best_supported_shift_laps": pd.NA,
        "best_hypothetical_pit_lap": pd.NA,
        "estimated_gain_vs_actual_sec": np.nan,
        "best_delta_p25_sec": np.nan,
        "best_delta_p75_sec": np.nan,
        "best_shift_win_pct": np.nan,
        "best_earlier_delta_sec": np.nan,
        "best_later_delta_sec": np.nan,
        "supported_scenarios": 0,
        "bootstrap_requested_samples": 0,
        "bootstrap_valid_samples": 0,
        "bootstrap_attempted_samples": 0,
        "boundary_minimum": False,
        "best_old_extrapolation_laps": np.nan,
        "best_new_extrapolation_laps": np.nan,
        "actual_old_extrapolation_laps": np.nan,
        "actual_new_extrapolation_laps": np.nan,
        "old_reference_laps": old_count,
        "new_mature_reference_laps": mature_count,
        "warmup_profile_laps": warmup_count,
        "old_slope_sec_per_tyre_lap": np.nan,
        "new_slope_sec_per_stint_lap": np.nan,
        "old_model_mad_sec": np.nan,
        "new_model_mad_sec": np.nan,
        "replay_coverage_pct": np.nan,
        "field_peer_count_median": np.nan,
        "timing_signal": "Insufficient evidence",
        "eligible": False,
        "exclusion_reason": reason,
        "confidence": "insufficient",
        "methodology_version": METHODOLOGY_VERSION,
    }


def _confidence(
    transition: pd.Series,
    old_count: int,
    mature_count: int,
    coverage: float,
    old_mad: float,
    new_mad: float,
    win_pct: float,
    boundary_minimum: bool,
    valid_samples: int,
) -> str:
    if (
        old_count >= 6
        and mature_count >= 4
        and bool(transition["new_tyre_fresh"])
        and coverage >= 90
        and old_mad <= 0.25
        and new_mad <= 0.25
        and win_pct >= 70
        and not boundary_minimum
        and valid_samples >= 300
    ):
        return "high"
    return "medium"


def analyse_pit_timing_sensitivity(
    laps: pd.DataFrame,
    replay: pd.DataFrame,
    stops: pd.DataFrame | None = None,
    *,
    min_field_peers: int = MIN_FIELD_PEERS,
    min_replay_coverage_pct: float = MIN_REPLAY_COVERAGE_PCT,
    bootstrap_samples: int = BOOTSTRAP_SAMPLES,
    random_seed: int = 0,
    max_old_extrapolation_laps: float = MAX_OLD_EXTRAPOLATION_LAPS,
    max_new_extrapolation_laps: float = MAX_NEW_EXTRAPOLATION_LAPS,
) -> PitTimingSensitivityResult:
    """Estimate ±3-lap pit-timing scenarios from observed clean-air pace."""
    _require_columns(laps, _LAP_REQUIRED, "laps")
    _require_columns(replay, _REPLAY_REQUIRED, "replay")
    if min_field_peers < 1:
        raise ValueError("min_field_peers must be positive")
    if min_replay_coverage_pct <= 0 or min_replay_coverage_pct > 100:
        raise ValueError("min_replay_coverage_pct must be in (0, 100]")
    if bootstrap_samples < 1:
        raise ValueError("bootstrap_samples must be positive")
    for name, value in (
        ("max_old_extrapolation_laps", max_old_extrapolation_laps),
        ("max_new_extrapolation_laps", max_new_extrapolation_laps),
    ):
        if not np.isfinite(value) or value < 0:
            raise ValueError(f"{name} must be finite and non-negative")
    if laps.empty:
        return _empty_result()

    prepared = _prepare_laps(laps)
    if not {"is_pit_in_lap", "is_pit_out_lap", "is_pit_boundary"}.issubset(prepared.columns):
        prepared = attach_pit_lap_context(prepared, build_pit_lap_context(prepared, stops))
    transitions = _attach_stop_context(_derive_transitions(prepared), stops)
    if transitions.empty:
        return _empty_result()
    residuals = _add_field_residuals(
        prepared,
        replay,
        min_field_peers=min_field_peers,
        min_replay_coverage_pct=min_replay_coverage_pct,
    )
    summary_rows: list[dict[str, object]] = []
    scenario_rows: list[dict[str, object]] = []
    for _, transition in transitions.iterrows():
        driver_laps = prepared.loc[
            prepared["season"].eq(transition["season"])
            & prepared["round"].eq(transition["round"])
            & prepared["driver_code"].eq(transition["driver_code"])
        ]
        race_transitions = transitions.loc[
            transitions["season"].eq(transition["season"])
            & transitions["round"].eq(transition["round"])
        ]
        reason = _base_exclusion(transition, driver_laps, race_transitions)
        if reason:
            summary_rows.append(_excluded_summary(transition, reason))
            scenario_rows.extend(_unsupported_scenarios(transition, reason))
            continue
        model, reason, old, mature, warmup = _build_model(transition, driver_laps, residuals)
        if model is None:
            summary_rows.append(
                _excluded_summary(transition, reason, len(old), len(mature), len(warmup))
            )
            scenario_rows.extend(_unsupported_scenarios(transition, reason))
            continue

        out_lap = int(transition["actual_out_lap"])
        costs = {shift: _scenario_cost(model, out_lap, shift) for shift in SCENARIO_SHIFTS}
        deltas = {shift: costs[shift] - costs[0] for shift in SCENARIO_SHIFTS}
        distances = {
            shift: _extrapolation_distances(model, old, mature, out_lap, shift)
            for shift in SCENARIO_SHIFTS
        }
        reasons = {
            shift: (
                "old_reference_extrapolation_limit"
                if distance[0] > max_old_extrapolation_laps
                else "new_reference_extrapolation_limit"
                if distance[1] > max_new_extrapolation_laps
                else "nonfinite_scenario_model"
                if not np.isfinite(costs[shift]) or not np.isfinite(deltas[shift])
                else ""
            )
            for shift, distance in distances.items()
        }
        supported = [shift for shift in SCENARIO_SHIFTS if not reasons[shift]]
        excluded_reason = (
            "unsupported_actual_baseline"
            if reasons[0]
            else "no_supported_alternative"
            if len(supported) < 2
            else ""
        )
        if excluded_reason:
            summary = _excluded_summary(
                transition, excluded_reason, len(old), len(mature), len(warmup)
            )
            summary.update(
                actual_old_extrapolation_laps=distances[0][0],
                actual_new_extrapolation_laps=distances[0][1],
            )
            summary_rows.append(summary)
            excluded = _unsupported_scenarios(transition, excluded_reason)
            for row in excluded:
                shift = int(str(row["shift_laps"]))
                row.update(
                    old_extrapolation_laps=distances[shift][0],
                    new_extrapolation_laps=distances[shift][1],
                )
            scenario_rows.extend(excluded)
            continue
        seed_key = ":".join(str(transition[key]) for key in (*_DRIVER_KEYS, "stop_number"))
        seed = int.from_bytes(hashlib.sha256(seed_key.encode()).digest()[:8], "little")
        bootstrap = _bootstrap_deltas(
            old,
            mature,
            warmup,
            actual_in_age=model.actual_in_age,
            actual_out_lap=out_lap,
            samples=bootstrap_samples,
            seed=(random_seed + seed) % (2**64),
        )
        if (
            bootstrap.valid < MIN_BOOTSTRAP_VALID_SAMPLES
            or bootstrap.valid < bootstrap_samples * MIN_BOOTSTRAP_COMPLETION
        ):
            reason = "insufficient_valid_bootstrap_samples"
            summary = _excluded_summary(transition, reason, len(old), len(mature), len(warmup))
            summary.update(
                bootstrap_requested_samples=bootstrap.requested,
                bootstrap_valid_samples=bootstrap.valid,
                bootstrap_attempted_samples=bootstrap.attempted,
                actual_old_extrapolation_laps=distances[0][0],
                actual_new_extrapolation_laps=distances[0][1],
            )
            summary_rows.append(summary)
            excluded = _unsupported_scenarios(transition, reason)
            for row in excluded:
                shift = int(str(row["shift_laps"]))
                row.update(
                    old_extrapolation_laps=distances[shift][0],
                    new_extrapolation_laps=distances[shift][1],
                )
            scenario_rows.extend(excluded)
            continue
        samples = bootstrap.deltas
        best = _best_shift({shift: costs[shift] for shift in supported})
        boundary = best != 0 and best in (min(supported), max(supported))
        best_samples = samples[best]
        best_p25 = float(np.quantile(best_samples, 0.25))
        best_p75 = float(np.quantile(best_samples, 0.75))
        win_credit = 0.0
        for sample_index in range(len(best_samples)):
            sample_costs = {shift: float(samples[shift][sample_index]) for shift in supported}
            minima = _tied_minima(sample_costs)
            if best in minima:
                win_credit += 1 / len(minima)
        win_pct = 100.0 * win_credit / len(best_samples)
        gain = -deltas[best]
        meaningful = best != 0 and gain >= MEANINGFUL_GAIN_SEC and best_p75 < 0
        timing_signal = (
            "Earlier edge favoured; optimum unlocated"
            if meaningful and best < 0 and boundary
            else "Later edge favoured; optimum unlocated"
            if meaningful and best > 0 and boundary
            else "Earlier stop supported"
            if meaningful and best < 0
            else "Later stop supported"
            if meaningful and best > 0
            else "No meaningful directional signal"
        )
        evidence = pd.concat([old, mature, warmup], ignore_index=True)
        coverage = float(evidence["replay_coverage_pct"].median())
        peer_count = float(evidence["field_peer_count"].median())
        for shift in SCENARIO_SHIFTS:
            if reasons[shift]:
                row = _unsupported_scenarios(transition, reasons[shift])[shift + 3]
                row.update(
                    old_extrapolation_laps=distances[shift][0],
                    new_extrapolation_laps=distances[shift][1],
                )
                scenario_rows.append(row)
                continue
            distribution = samples[shift]
            scenario_rows.append(
                {
                    "season": transition["season"],
                    "round": transition["round"],
                    "race_name": transition["race_name"],
                    "driver_code": transition["driver_code"],
                    "driver_name": transition["driver_name"],
                    "team": transition["team"],
                    "stop_number": transition["stop_number"],
                    "actual_pit_lap": transition["actual_pit_lap"],
                    "actual_out_lap": transition["actual_out_lap"],
                    "shift_laps": shift,
                    "hypothetical_pit_lap": int(transition["actual_pit_lap"]) + shift,
                    "hypothetical_out_lap": out_lap + shift,
                    "estimated_cost_index_sec": costs[shift],
                    "delta_vs_actual_sec": deltas[shift],
                    "estimated_gain_vs_actual_sec": -deltas[shift],
                    "delta_p25_sec": float(np.quantile(distribution, 0.25)),
                    "delta_p75_sec": float(np.quantile(distribution, 0.75)),
                    "old_tyre_extension_laps": max(shift, 0),
                    "old_extrapolation_laps": distances[shift][0],
                    "new_extrapolation_laps": distances[shift][1],
                    "supported": True,
                    "exclusion_reason": "",
                    "methodology_version": METHODOLOGY_VERSION,
                }
            )
        summary_rows.append(
            {
                **_summary_base(transition),
                "best_supported_shift_laps": best,
                "best_hypothetical_pit_lap": int(transition["actual_pit_lap"]) + best,
                "estimated_gain_vs_actual_sec": gain,
                "best_delta_p25_sec": best_p25,
                "best_delta_p75_sec": best_p75,
                "best_shift_win_pct": win_pct,
                "best_earlier_delta_sec": min(
                    (deltas[shift] for shift in supported if shift < 0), default=np.nan
                ),
                "best_later_delta_sec": min(
                    (deltas[shift] for shift in supported if shift > 0), default=np.nan
                ),
                "supported_scenarios": len(supported),
                "bootstrap_requested_samples": bootstrap.requested,
                "bootstrap_valid_samples": bootstrap.valid,
                "bootstrap_attempted_samples": bootstrap.attempted,
                "boundary_minimum": boundary,
                "best_old_extrapolation_laps": distances[best][0],
                "best_new_extrapolation_laps": distances[best][1],
                "actual_old_extrapolation_laps": distances[0][0],
                "actual_new_extrapolation_laps": distances[0][1],
                "old_reference_laps": len(old),
                "new_mature_reference_laps": len(mature),
                "warmup_profile_laps": len(warmup),
                "old_slope_sec_per_tyre_lap": model.old_slope,
                "new_slope_sec_per_stint_lap": model.new_slope,
                "old_model_mad_sec": model.old_mad,
                "new_model_mad_sec": model.new_mad,
                "replay_coverage_pct": coverage,
                "field_peer_count_median": peer_count,
                "timing_signal": timing_signal,
                "eligible": True,
                "exclusion_reason": "",
                "confidence": _confidence(
                    transition,
                    len(old),
                    len(mature),
                    coverage,
                    model.old_mad,
                    model.new_mad,
                    win_pct,
                    boundary,
                    bootstrap.valid,
                ),
                "methodology_version": METHODOLOGY_VERSION,
            }
        )

    summary = pd.DataFrame(summary_rows, columns=PIT_TIMING_COLUMNS).sort_values(
        ["season", "round", "driver_code", "stop_number"]
    )
    # The request is known even when a pre-model exclusion prevents any draws.
    summary["bootstrap_requested_samples"] = bootstrap_samples
    scenarios = pd.DataFrame(scenario_rows, columns=PIT_TIMING_SCENARIO_COLUMNS).sort_values(
        ["season", "round", "driver_code", "stop_number", "shift_laps"]
    )
    return PitTimingSensitivityResult(
        summary=summary.reset_index(drop=True), scenarios=scenarios.reset_index(drop=True)
    )
