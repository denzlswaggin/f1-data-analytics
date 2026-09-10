"""Estimate how post-stop pace settles after the first full flying lap.

The recorded first lap of a stint can include stationary pit time, so offset 0
is retained only as the inferred out-lap. A robust mature-pacing trend from
clean-air offsets 7--12 is extrapolated back across evaluation offsets 1--6.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

METHODOLOGY_VERSION = "tyre-warmup-v2"
STABLE_BAND_SEC = 0.50
MIN_STINT_LAPS = 11
MIN_REPLAY_COVERAGE_PCT = 80.0
MAX_BASELINE_SLOPE_SEC_PER_LAP = 0.50
MAX_BASELINE_MAD_SEC = 0.50
SUPPORTED_COMPOUNDS = {"SOFT", "MEDIUM", "HARD"}

_KEYS = ["season", "round", "driver_code", "stint"]
_LAP_KEYS = [*_KEYS, "lap_number"]
_LAPS_REQUIRED = {
    *_KEYS,
    "race_name",
    "driver_name",
    "team",
    "lap_number",
    "compound",
    "tyre_life",
    "is_fresh_tyre",
    "lap_time_sec",
    "track_status",
}
_TRAFFIC_REQUIRED = {
    *_LAP_KEYS,
    "air_state",
    "replay_coverage_pct",
    "traffic_share",
    "median_gap_to_ahead_s",
    "controlled_pace_delta_sec",
}

TYRE_WARMUP_COLUMNS = [
    "season",
    "round",
    "race_name",
    "driver_code",
    "driver_name",
    "team",
    "stint",
    "compound",
    "is_fresh_tyre",
    "out_lap",
    "stint_start_lap",
    "stint_end_lap",
    "stint_laps",
    "contiguous_stint_transition",
    "clean_evaluation_laps",
    "traffic_evaluation_laps",
    "mature_reference_laps",
    "baseline_slope_sec_per_lap",
    "baseline_intercept_sec",
    "baseline_mad_sec",
    "first_flying_warmup_loss_sec",
    "second_flying_warmup_loss_sec",
    "first_two_lap_warmup_cost_sec",
    "stable_band_sec",
    "stable_window_start_lap",
    "time_to_pace_laps",
    "stable_pace_achieved",
    "right_censored",
    "observation_complete",
    "warmup_eligible",
    "crossover_eligible",
    "exclusion_reason",
    "confidence",
    "replay_coverage_pct",
    "methodology_version",
]

TYRE_WARMUP_LAP_COLUMNS = [
    "season",
    "round",
    "race_name",
    "driver_code",
    "driver_name",
    "team",
    "stint",
    "compound",
    "is_fresh_tyre",
    "out_lap",
    "lap_number",
    "post_stop_offset",
    "tyre_life",
    "lap_time_sec",
    "track_status",
    "air_state",
    "replay_coverage_pct",
    "traffic_share",
    "median_gap_to_ahead_s",
    "controlled_pace_delta_sec",
    "expected_mature_delta_sec",
    "warmup_loss_sec",
    "used_for_baseline",
    "within_stable_band",
    "lap_eligible",
    "lap_exclusion_reason",
    "methodology_version",
]

_SUMMARY_INTEGER = {
    "season",
    "round",
    "stint",
    "out_lap",
    "stint_start_lap",
    "stint_end_lap",
    "stint_laps",
    "clean_evaluation_laps",
    "traffic_evaluation_laps",
    "mature_reference_laps",
    "stable_window_start_lap",
    "time_to_pace_laps",
}
_SUMMARY_FLOAT = {
    "baseline_slope_sec_per_lap",
    "baseline_intercept_sec",
    "baseline_mad_sec",
    "first_flying_warmup_loss_sec",
    "second_flying_warmup_loss_sec",
    "first_two_lap_warmup_cost_sec",
    "stable_band_sec",
    "replay_coverage_pct",
}
_SUMMARY_BOOLEAN = {
    "is_fresh_tyre",
    "contiguous_stint_transition",
    "stable_pace_achieved",
    "right_censored",
    "observation_complete",
    "warmup_eligible",
    "crossover_eligible",
}
_LAP_INTEGER = {
    "season",
    "round",
    "stint",
    "out_lap",
    "lap_number",
    "post_stop_offset",
    "tyre_life",
}
_LAP_FLOAT = {
    "lap_time_sec",
    "replay_coverage_pct",
    "traffic_share",
    "median_gap_to_ahead_s",
    "controlled_pace_delta_sec",
    "expected_mature_delta_sec",
    "warmup_loss_sec",
}
_LAP_BOOLEAN = {
    "is_fresh_tyre",
    "used_for_baseline",
    "within_stable_band",
    "lap_eligible",
}


@dataclass(frozen=True)
class TyreWarmupResult:
    """Per-stint conclusions and the lap evidence behind them."""

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


def _empty_result() -> TyreWarmupResult:
    return TyreWarmupResult(
        summary=_typed_empty(
            TYRE_WARMUP_COLUMNS, _SUMMARY_INTEGER, _SUMMARY_FLOAT, _SUMMARY_BOOLEAN
        ),
        laps=_typed_empty(TYRE_WARMUP_LAP_COLUMNS, _LAP_INTEGER, _LAP_FLOAT, _LAP_BOOLEAN),
    )


def _require_columns(frame: pd.DataFrame, required: set[str], name: str) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{name} is missing columns: {sorted(missing)}")


def _cast_frame(
    frame: pd.DataFrame,
    columns: list[str],
    integers: set[str],
    floats: set[str],
    booleans: set[str],
) -> pd.DataFrame:
    if frame.empty:
        return _typed_empty(columns, integers, floats, booleans)
    result = frame.loc[:, columns].copy()
    for column in integers:
        result[column] = pd.to_numeric(result[column], errors="coerce").astype("Int64")
    for column in floats:
        result[column] = pd.to_numeric(result[column], errors="coerce").astype("float64")
    for column in booleans:
        result[column] = result[column].astype("boolean")
    for column in set(columns) - integers - floats - booleans:
        result[column] = result[column].astype("string")
    return result


def _theil_sen_trend(offsets: pd.Series, values: pd.Series) -> tuple[float, float, float]:
    x = offsets.to_numpy(dtype=float)
    y = values.to_numpy(dtype=float)
    slopes = [
        (y[j] - y[i]) / (x[j] - x[i])
        for i in range(len(x))
        for j in range(i + 1, len(x))
        if x[j] != x[i]
    ]
    slope = float(np.median(slopes))
    intercept = float(np.median(y - slope * x))
    mad = float(np.median(np.abs(y - (intercept + slope * x))))
    return slope, intercept, mad


def _first_stable_pair(valid_losses: dict[int, float], threshold: float) -> int | None:
    for offset in range(1, 6):
        if offset not in valid_losses or offset + 1 not in valid_losses:
            continue
        if abs(valid_losses[offset]) <= threshold and abs(valid_losses[offset + 1]) <= threshold:
            return offset
    return None


def _summary_exclusion_reason(
    *,
    compound: str,
    contiguous_transition: bool,
    stint_laps: int,
    first: pd.Series | None,
    mature_points: int,
    slope: float,
    mad: float,
) -> str:
    if compound not in SUPPORTED_COMPOUNDS:
        return "Unsupported or wet-weather compound"
    if not contiguous_transition:
        return "Stint transition is not contiguous"
    if stint_laps < MIN_STINT_LAPS:
        return f"Stint shorter than {MIN_STINT_LAPS} laps"
    if first is None:
        return "First flying lap unavailable"
    if pd.notna(first.get("is_pit_boundary")) and bool(first.get("is_pit_boundary")):
        return "First flying lap was a pit boundary"
    if str(first["track_status"]) != "1":
        return "First flying lap was not green"
    if pd.isna(first["controlled_pace_delta_sec"]):
        return "Traffic context unavailable on first flying lap"
    if str(first["air_state"]) != "clean_air":
        return "First flying lap was not in clean air"
    if (
        pd.isna(first["replay_coverage_pct"])
        or float(first["replay_coverage_pct"]) < MIN_REPLAY_COVERAGE_PCT
    ):
        return "Replay coverage below 80% on first flying lap"
    if mature_points < 3:
        return "Fewer than three clean mature-reference laps"
    if abs(slope) > MAX_BASELINE_SLOPE_SEC_PER_LAP:
        return "Mature-pace trend is too steep"
    if mad > MAX_BASELINE_MAD_SEC:
        return "Mature-pace trend is too noisy"
    return ""


def analyse_tyre_warmup(
    laps: pd.DataFrame,
    traffic_laps: pd.DataFrame,
    *,
    stable_band_sec: float = STABLE_BAND_SEC,
) -> TyreWarmupResult:
    """Measure settling loss and time to a stable mature-pace band."""
    _require_columns(laps, _LAPS_REQUIRED, "laps")
    _require_columns(traffic_laps, _TRAFFIC_REQUIRED, "traffic_laps")
    if stable_band_sec <= 0:
        raise ValueError("stable_band_sec must be greater than zero")
    if laps.empty:
        return _empty_result()

    prepared_laps = laps.copy()
    prepared_traffic = traffic_laps.copy()
    for frame in (prepared_laps, prepared_traffic):
        for column in ("season", "round", "stint", "lap_number"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in ("tyre_life", "lap_time_sec"):
        prepared_laps[column] = pd.to_numeric(prepared_laps[column], errors="coerce")
    for column in (
        "replay_coverage_pct",
        "traffic_share",
        "median_gap_to_ahead_s",
        "controlled_pace_delta_sec",
    ):
        prepared_traffic[column] = pd.to_numeric(prepared_traffic[column], errors="coerce")

    prepared_laps = prepared_laps.dropna(subset=_LAP_KEYS).drop_duplicates(_LAP_KEYS, keep="last")
    prepared_laps = prepared_laps.sort_values(["season", "round", "driver_code", "lap_number"])
    driver_keys = ["season", "round", "driver_code"]
    prepared_laps["_previous_lap"] = prepared_laps.groupby(driver_keys)["lap_number"].shift()
    prepared_laps["_previous_stint"] = prepared_laps.groupby(driver_keys)["stint"].shift()
    traffic_context = prepared_traffic.loc[
        :,
        [
            *_LAP_KEYS,
            "air_state",
            "replay_coverage_pct",
            "traffic_share",
            "median_gap_to_ahead_s",
            "controlled_pace_delta_sec",
        ],
    ].drop_duplicates(_LAP_KEYS, keep="last")
    prepared = prepared_laps.merge(
        traffic_context,
        on=_LAP_KEYS,
        how="left",
        validate="one_to_one",
    ).sort_values([*_KEYS, "lap_number"])

    summary_rows: list[dict[str, object]] = []
    lap_rows: list[dict[str, object]] = []
    for keys, stint in prepared.groupby(_KEYS, sort=True):
        season, rnd, driver_code, stint_number = keys
        if int(stint_number) <= 1:
            continue
        first_stint_row = stint.iloc[0]
        start_lap = int(first_stint_row["lap_number"])
        end_lap = int(stint["lap_number"].max())
        stint_laps = int(stint["lap_number"].nunique())
        contiguous_transition = bool(
            pd.notna(first_stint_row["_previous_lap"])
            and int(first_stint_row["_previous_lap"]) == start_lap - 1
            and pd.notna(first_stint_row["_previous_stint"])
            and int(first_stint_row["_previous_stint"]) < int(stint_number)
        )
        compound_values = stint["compound"].dropna().astype("string")
        compound = str(compound_values.iloc[0]).upper() if not compound_values.empty else "UNKNOWN"
        is_fresh_tyre = bool(first_stint_row["is_fresh_tyre"])
        window = stint.loc[stint["lap_number"].sub(start_lap).between(1, 12)].copy()
        window["post_stop_offset"] = window["lap_number"].sub(start_lap).astype(int)
        window["context_eligible"] = (
            window["track_status"].astype("string").eq("1")
            & window["air_state"].astype("string").eq("clean_air")
            & window["controlled_pace_delta_sec"].notna()
            & window["replay_coverage_pct"].ge(MIN_REPLAY_COVERAGE_PCT).fillna(False)
            & ~window.get("is_pit_boundary", pd.Series(False, index=window.index)).fillna(False)
        )
        evaluation = window["post_stop_offset"].between(1, 6)
        mature_mask = window["post_stop_offset"].between(7, 12)
        mature = window.loc[mature_mask & window["context_eligible"]]
        if len(mature) >= 3:
            slope, intercept, baseline_mad = _theil_sen_trend(
                mature["post_stop_offset"], mature["controlled_pace_delta_sec"]
            )
        else:
            slope, intercept, baseline_mad = np.nan, np.nan, np.nan
        first_rows = window.loc[window["post_stop_offset"].eq(1)]
        first = first_rows.iloc[0] if not first_rows.empty else None
        reason = _summary_exclusion_reason(
            compound=compound,
            contiguous_transition=contiguous_transition,
            stint_laps=stint_laps,
            first=first,
            mature_points=len(mature),
            slope=slope,
            mad=baseline_mad,
        )
        warmup_eligible = not reason
        valid_losses: dict[int, float] = {}
        if warmup_eligible:
            for row in window.loc[window["context_eligible"]].itertuples(index=False):
                offset = int(row.post_stop_offset)
                expected = intercept + slope * offset
                valid_losses[offset] = float(row.controlled_pace_delta_sec) - expected

        stable_start = _first_stable_pair(valid_losses, stable_band_sec)
        stable_pace_achieved = bool(warmup_eligible and stable_start is not None)
        observation_complete = bool(
            warmup_eligible and all(offset in valid_losses for offset in range(1, 7))
        )
        right_censored = bool(warmup_eligible and not stable_pace_achieved and observation_complete)
        crossover_eligible = bool(stable_pace_achieved or right_censored)
        first_loss = valid_losses.get(1, np.nan)
        second_loss = valid_losses.get(2, np.nan)
        first_two_cost = (
            max(0.0, first_loss) + max(0.0, second_loss)
            if np.isfinite(first_loss) and np.isfinite(second_loss)
            else np.nan
        )
        coverage = pd.to_numeric(window["replay_coverage_pct"], errors="coerce").median()
        confirmation_offset = stable_start + 1 if stable_start is not None else 6
        continuous_to_confirmation = all(
            offset in valid_losses for offset in range(1, confirmation_offset + 1)
        )
        high_confidence = bool(
            warmup_eligible
            and is_fresh_tyre
            and len(mature) >= 4
            and baseline_mad <= 0.25
            and pd.notna(coverage)
            and coverage >= 90
            and continuous_to_confirmation
        )
        confidence = "High" if high_confidence else "Medium" if warmup_eligible else "Insufficient"

        summary_rows.append(
            {
                "season": int(season),
                "round": int(rnd),
                "race_name": str(stint["race_name"].iloc[0]),
                "driver_code": str(driver_code),
                "driver_name": str(stint["driver_name"].iloc[0]),
                "team": str(stint["team"].iloc[0]),
                "stint": int(stint_number),
                "compound": compound,
                "is_fresh_tyre": is_fresh_tyre,
                "out_lap": start_lap,
                "stint_start_lap": start_lap,
                "stint_end_lap": end_lap,
                "stint_laps": stint_laps,
                "contiguous_stint_transition": contiguous_transition,
                "clean_evaluation_laps": int((evaluation & window["context_eligible"]).sum()),
                "traffic_evaluation_laps": int(
                    (evaluation & window["air_state"].isin(["traffic", "mixed"])).sum()
                ),
                "mature_reference_laps": len(mature),
                "baseline_slope_sec_per_lap": slope,
                "baseline_intercept_sec": intercept,
                "baseline_mad_sec": baseline_mad,
                "first_flying_warmup_loss_sec": first_loss,
                "second_flying_warmup_loss_sec": second_loss,
                "first_two_lap_warmup_cost_sec": first_two_cost,
                "stable_band_sec": stable_band_sec,
                "stable_window_start_lap": (
                    start_lap + stable_start if stable_start is not None else None
                ),
                "time_to_pace_laps": stable_start + 1 if stable_start is not None else None,
                "stable_pace_achieved": stable_pace_achieved,
                "right_censored": right_censored,
                "observation_complete": observation_complete,
                "warmup_eligible": warmup_eligible,
                "crossover_eligible": crossover_eligible,
                "exclusion_reason": reason,
                "confidence": confidence,
                "replay_coverage_pct": coverage,
                "methodology_version": METHODOLOGY_VERSION,
            }
        )

        for row in window.itertuples(index=False):
            offset = int(row.post_stop_offset)
            used_for_baseline = bool(7 <= offset <= 12 and row.context_eligible)
            expected = intercept + slope * offset if np.isfinite(slope) else np.nan
            loss = valid_losses.get(offset, np.nan)
            lap_reason = ""
            if pd.notna(getattr(row, "is_pit_boundary", False)) and bool(
                getattr(row, "is_pit_boundary", False)
            ):
                lap_reason = "Pit entry or exit lap"
            elif str(row.track_status) != "1":
                lap_reason = "Lap was not green"
            elif pd.isna(row.controlled_pace_delta_sec):
                lap_reason = "Traffic context unavailable"
            elif str(row.air_state) != "clean_air":
                lap_reason = "Lap was not in clean air"
            elif (
                pd.isna(row.replay_coverage_pct)
                or row.replay_coverage_pct < MIN_REPLAY_COVERAGE_PCT
            ):
                lap_reason = "Replay coverage below 80%"
            elif not warmup_eligible:
                lap_reason = reason
            lap_eligible = bool(warmup_eligible and row.context_eligible)
            lap_rows.append(
                {
                    "season": int(season),
                    "round": int(rnd),
                    "race_name": str(row.race_name),
                    "driver_code": str(driver_code),
                    "driver_name": str(row.driver_name),
                    "team": str(row.team),
                    "stint": int(stint_number),
                    "compound": compound,
                    "is_fresh_tyre": is_fresh_tyre,
                    "out_lap": start_lap,
                    "lap_number": int(row.lap_number),
                    "post_stop_offset": offset,
                    "tyre_life": row.tyre_life,
                    "lap_time_sec": row.lap_time_sec,
                    "track_status": str(row.track_status),
                    "air_state": str(row.air_state) if pd.notna(row.air_state) else "unavailable",
                    "replay_coverage_pct": row.replay_coverage_pct,
                    "traffic_share": row.traffic_share,
                    "median_gap_to_ahead_s": row.median_gap_to_ahead_s,
                    "controlled_pace_delta_sec": row.controlled_pace_delta_sec,
                    "expected_mature_delta_sec": expected,
                    "warmup_loss_sec": loss,
                    "used_for_baseline": used_for_baseline,
                    "within_stable_band": bool(
                        lap_eligible and np.isfinite(loss) and abs(loss) <= stable_band_sec
                    ),
                    "lap_eligible": lap_eligible,
                    "lap_exclusion_reason": lap_reason,
                    "methodology_version": METHODOLOGY_VERSION,
                }
            )

    return TyreWarmupResult(
        summary=_cast_frame(
            pd.DataFrame(summary_rows),
            TYRE_WARMUP_COLUMNS,
            _SUMMARY_INTEGER,
            _SUMMARY_FLOAT,
            _SUMMARY_BOOLEAN,
        ),
        laps=_cast_frame(
            pd.DataFrame(lap_rows),
            TYRE_WARMUP_LAP_COLUMNS,
            _LAP_INTEGER,
            _LAP_FLOAT,
            _LAP_BOOLEAN,
        ),
    )
