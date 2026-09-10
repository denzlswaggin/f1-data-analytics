"""Traffic-controlled tyre warm-up after a racing pit stop.

The first lap of a new stint is treated as the out-lap because its recorded lap
time can include stationary pit time. Analysis starts on the following full lap
and compares its controlled pace with laps three to five of the same stint.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

METHODOLOGY_VERSION = "tyre-warmup-v1"
STABLE_BAND_SEC = 0.30
SUPPORTED_COMPOUNDS = {"SOFT", "MEDIUM", "HARD"}
MIN_STINT_LAPS = 7

_KEYS = ["season", "round", "driver_code", "stint"]
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
    *_KEYS,
    "lap_number",
    "air_state",
    "controlled_pace_delta_sec",
    "replay_coverage_pct",
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
    "stint_start_lap",
    "stint_end_lap",
    "stint_laps",
    "started_fresh",
    "first_flying_lap",
    "baseline_laps",
    "clean_air_samples_first5",
    "stable_baseline_controlled_delta_sec",
    "first_flying_loss_sec",
    "second_flying_loss_sec",
    "first_two_lap_warmup_cost_sec",
    "time_to_stable_laps",
    "stable_band_threshold_sec",
    "replay_coverage_pct",
    "eligible",
    "exclusion_reason",
    "confidence",
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
    "lap_number",
    "stint_lap_offset",
    "phase",
    "tyre_life",
    "lap_time_sec",
    "track_green",
    "air_state",
    "replay_coverage_pct",
    "controlled_pace_delta_sec",
    "stable_baseline_controlled_delta_sec",
    "warmup_delta_sec",
    "within_stable_band",
    "eligible",
    "exclusion_reason",
    "methodology_version",
]

_SUMMARY_INTEGER = {
    "season",
    "round",
    "stint",
    "stint_start_lap",
    "stint_end_lap",
    "stint_laps",
    "first_flying_lap",
    "baseline_laps",
    "clean_air_samples_first5",
    "time_to_stable_laps",
}
_SUMMARY_FLOAT = {
    "stable_baseline_controlled_delta_sec",
    "first_flying_loss_sec",
    "second_flying_loss_sec",
    "first_two_lap_warmup_cost_sec",
    "stable_band_threshold_sec",
    "replay_coverage_pct",
}
_SUMMARY_BOOLEAN = {"started_fresh", "eligible"}
_LAP_INTEGER = {"season", "round", "stint", "lap_number", "stint_lap_offset", "tyre_life"}
_LAP_FLOAT = {
    "lap_time_sec",
    "replay_coverage_pct",
    "controlled_pace_delta_sec",
    "stable_baseline_controlled_delta_sec",
    "warmup_delta_sec",
}
_LAP_BOOLEAN = {"track_green", "within_stable_band", "eligible"}


@dataclass(frozen=True)
class TyreWarmupResult:
    """Per-stint conclusions and their first-five-lap evidence."""

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


def _phase(offset: int) -> str:
    if offset == 1:
        return "First flying lap"
    if offset == 2:
        return "Second flying lap"
    return "Settling window"


def _exclusion_reason(
    *,
    compound: str,
    started_fresh: bool,
    stint_laps: int,
    first: pd.Series | None,
    baseline_laps: int,
) -> str:
    if compound not in SUPPORTED_COMPOUNDS:
        return "Unsupported or wet-weather compound"
    if not started_fresh:
        return "Stint did not start on fresh tyres"
    if stint_laps < MIN_STINT_LAPS:
        return f"Stint shorter than {MIN_STINT_LAPS} laps"
    if first is None:
        return "First flying lap unavailable"
    if not bool(first["track_green"]):
        return "First flying lap was not green"
    if pd.isna(first["controlled_pace_delta_sec"]):
        return "Traffic context unavailable on first flying lap"
    if str(first["air_state"]) != "clean_air":
        return "First flying lap was not in clean air"
    if baseline_laps < 2:
        return "Fewer than two clean baseline laps"
    return ""


def _time_to_stable(valid_deltas: dict[int, float], threshold: float) -> int | None:
    for offset in range(1, 5):
        current = valid_deltas.get(offset)
        following = valid_deltas.get(offset + 1)
        if (
            current is not None
            and following is not None
            and abs(current) <= threshold
            and abs(following) <= threshold
        ):
            return offset
    return None


def analyse_tyre_warmup(
    laps: pd.DataFrame,
    traffic_laps: pd.DataFrame,
    *,
    stable_band_sec: float = STABLE_BAND_SEC,
) -> TyreWarmupResult:
    """Measure first-flying-lap loss and time to a stable pace band."""
    _require_columns(laps, _LAPS_REQUIRED, "laps")
    _require_columns(traffic_laps, _TRAFFIC_REQUIRED, "traffic_laps")
    if stable_band_sec <= 0:
        raise ValueError("stable_band_sec must be greater than zero")
    if laps.empty:
        return _empty_result()

    laps = laps.copy()
    traffic_laps = traffic_laps.copy()
    numeric_keys = ("season", "round", "stint", "lap_number")
    for frame in (laps, traffic_laps):
        for column in numeric_keys:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in ("tyre_life", "lap_time_sec"):
        laps[column] = pd.to_numeric(laps[column], errors="coerce")
    for column in ("controlled_pace_delta_sec", "replay_coverage_pct"):
        traffic_laps[column] = pd.to_numeric(traffic_laps[column], errors="coerce")
    lap_keys = [*_KEYS, "lap_number"]
    traffic_context = traffic_laps.loc[
        :,
        [*_KEYS, "lap_number", "air_state", "controlled_pace_delta_sec", "replay_coverage_pct"],
    ].drop_duplicates(lap_keys, keep="last")
    prepared = laps.drop_duplicates(lap_keys, keep="last").merge(
        traffic_context,
        on=lap_keys,
        how="left",
        validate="one_to_one",
    )
    prepared = prepared.dropna(subset=[*_KEYS, "lap_number"]).sort_values([*_KEYS, "lap_number"])

    summary_rows: list[dict[str, object]] = []
    lap_rows: list[dict[str, object]] = []
    for keys, stint in prepared.groupby(_KEYS, sort=True):
        season, rnd, driver_code, stint_number = keys
        if int(stint_number) <= 1:
            continue
        start_lap = int(stint["lap_number"].min())
        end_lap = int(stint["lap_number"].max())
        stint_laps = end_lap - start_lap + 1
        compound_values = stint["compound"].dropna().astype("string")
        compound = str(compound_values.iloc[0]).upper() if not compound_values.empty else "UNKNOWN"
        started_fresh = bool(stint["is_fresh_tyre"].fillna(False).astype(bool).any())
        window = stint.loc[stint["lap_number"].sub(start_lap).between(1, 5)].copy()
        window["stint_lap_offset"] = window["lap_number"].sub(start_lap).astype(int)
        window["track_green"] = window["track_status"].astype("string").eq("1")
        window["context_eligible"] = (
            window["track_green"]
            & window["air_state"].astype("string").eq("clean_air")
            & window["controlled_pace_delta_sec"].notna()
        )
        baseline = window.loc[
            window["stint_lap_offset"].between(3, 5) & window["context_eligible"],
            "controlled_pace_delta_sec",
        ]
        baseline_value = float(baseline.median()) if len(baseline) >= 2 else np.nan
        first_rows = window.loc[window["stint_lap_offset"].eq(1)]
        first = first_rows.iloc[0] if not first_rows.empty else None
        reason = _exclusion_reason(
            compound=compound,
            started_fresh=started_fresh,
            stint_laps=stint_laps,
            first=first,
            baseline_laps=len(baseline),
        )
        eligible = not reason
        valid_deltas: dict[int, float] = {}
        if np.isfinite(baseline_value):
            for row in window.loc[window["context_eligible"]].itertuples(index=False):
                valid_deltas[int(row.stint_lap_offset)] = (
                    float(row.controlled_pace_delta_sec) - baseline_value
                )
        time_to_stable = _time_to_stable(valid_deltas, stable_band_sec) if eligible else None
        first_loss = valid_deltas.get(1, np.nan) if eligible else np.nan
        second_loss = valid_deltas.get(2, np.nan) if eligible else np.nan
        first_two_cost = (
            max(0.0, first_loss) + max(0.0, second_loss)
            if np.isfinite(first_loss) and np.isfinite(second_loss)
            else np.nan
        )
        replay_coverage = pd.to_numeric(window["replay_coverage_pct"], errors="coerce").median()
        high_confidence = (
            eligible
            and len(baseline) == 3
            and set(valid_deltas) == {1, 2, 3, 4, 5}
            and pd.notna(replay_coverage)
            and replay_coverage >= 80
        )
        confidence = "High" if high_confidence else "Medium" if eligible else "Low"

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
                "stint_start_lap": start_lap,
                "stint_end_lap": end_lap,
                "stint_laps": stint_laps,
                "started_fresh": started_fresh,
                "first_flying_lap": start_lap + 1,
                "baseline_laps": len(baseline),
                "clean_air_samples_first5": len(valid_deltas),
                "stable_baseline_controlled_delta_sec": baseline_value,
                "first_flying_loss_sec": first_loss,
                "second_flying_loss_sec": second_loss,
                "first_two_lap_warmup_cost_sec": first_two_cost,
                "time_to_stable_laps": time_to_stable,
                "stable_band_threshold_sec": stable_band_sec,
                "replay_coverage_pct": replay_coverage,
                "eligible": eligible,
                "exclusion_reason": reason,
                "confidence": confidence,
                "methodology_version": METHODOLOGY_VERSION,
            }
        )
        for row in window.itertuples(index=False):
            offset = int(row.stint_lap_offset)
            lap_eligible = bool(eligible and row.context_eligible)
            lap_reason = ""
            if not bool(row.track_green):
                lap_reason = "Lap was not green"
            elif pd.isna(row.controlled_pace_delta_sec):
                lap_reason = "Traffic context unavailable"
            elif str(row.air_state) != "clean_air":
                lap_reason = "Lap was not in clean air"
            elif not eligible:
                lap_reason = reason
            delta = valid_deltas.get(offset, np.nan) if eligible else np.nan
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
                    "lap_number": int(row.lap_number),
                    "stint_lap_offset": offset,
                    "phase": _phase(offset),
                    "tyre_life": row.tyre_life,
                    "lap_time_sec": row.lap_time_sec,
                    "track_green": bool(row.track_green),
                    "air_state": str(row.air_state) if pd.notna(row.air_state) else "unavailable",
                    "replay_coverage_pct": row.replay_coverage_pct,
                    "controlled_pace_delta_sec": row.controlled_pace_delta_sec,
                    "stable_baseline_controlled_delta_sec": baseline_value,
                    "warmup_delta_sec": delta,
                    "within_stable_band": bool(
                        lap_eligible and np.isfinite(delta) and abs(delta) <= stable_band_sec
                    ),
                    "eligible": lap_eligible,
                    "exclusion_reason": lap_reason,
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
