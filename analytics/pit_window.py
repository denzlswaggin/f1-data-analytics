"""Pairwise pit-window effectiveness from race laps and stop timing.

The metric is descriptive rather than causal.  It compares the signed time gap
between two nearby rivals immediately before the first stop and after both cars
have completed their out-laps.  Race-control-affected or incomplete windows are
kept as evidence but excluded from the headline result.
"""

from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd

MAX_STOP_SEPARATION_LAPS = 3
MAX_PRE_GAP_SEC = 5.0
MAX_POSITION_DISTANCE = 1
OUTCOME_THRESHOLD_SEC = 0.5

_RACE_KEYS = ["season", "round"]
_DRIVER_KEYS = [*_RACE_KEYS, "driver_code"]
_LAP_REQUIRED = {
    *_DRIVER_KEYS,
    "race_name",
    "driver_name",
    "team",
    "lap_number",
    "stint",
    "compound",
    "is_fresh_tyre",
    "tyre_life",
    "position",
    "lap_start_sec",
    "lap_time_sec",
    "track_status",
}
_STOP_REQUIRED = {*_DRIVER_KEYS, "pit_lap", "duration_sec"}

PIT_WINDOW_COLUMNS = [
    "season",
    "round",
    "race_name",
    "stop_number",
    "early_driver_code",
    "early_driver_name",
    "early_team",
    "late_driver_code",
    "late_driver_name",
    "late_team",
    "early_pit_lap",
    "late_pit_lap",
    "stop_separation_laps",
    "checkpoint_before_lap",
    "checkpoint_after_lap",
    "early_old_compound",
    "early_new_compound",
    "late_old_compound",
    "late_new_compound",
    "early_new_tyre_fresh",
    "late_new_tyre_fresh",
    "position_before_early",
    "position_before_late",
    "position_after_early",
    "position_after_late",
    "gap_before_sec",
    "gap_after_sec",
    "net_time_gain_sec",
    "early_stop_duration_sec",
    "late_stop_duration_sec",
    "stop_duration_delta_sec",
    "on_track_gain_sec",
    "position_flip",
    "window_green",
    "eligible",
    "exclusion_reason",
    "confidence",
    "opportunity_type",
    "outcome_label",
    "methodology_version",
]

_INTEGER_COLUMNS = {
    "season",
    "round",
    "stop_number",
    "early_pit_lap",
    "late_pit_lap",
    "stop_separation_laps",
    "checkpoint_before_lap",
    "checkpoint_after_lap",
    "position_before_early",
    "position_before_late",
    "position_after_early",
    "position_after_late",
}
_FLOAT_COLUMNS = {
    "gap_before_sec",
    "gap_after_sec",
    "net_time_gain_sec",
    "early_stop_duration_sec",
    "late_stop_duration_sec",
    "stop_duration_delta_sec",
    "on_track_gain_sec",
}
_BOOLEAN_COLUMNS = {
    "early_new_tyre_fresh",
    "late_new_tyre_fresh",
    "position_flip",
    "window_green",
    "eligible",
}


def _require_columns(frame: pd.DataFrame, required: set[str], name: str) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{name} is missing columns: {sorted(missing)}")


def _empty_result() -> pd.DataFrame:
    return pd.DataFrame(
        {
            column: pd.Series(
                dtype=(
                    "Int64"
                    if column in _INTEGER_COLUMNS
                    else "float64"
                    if column in _FLOAT_COLUMNS
                    else "boolean"
                    if column in _BOOLEAN_COLUMNS
                    else "string"
                )
            )
            for column in PIT_WINDOW_COLUMNS
        }
    )


def _prepare_laps(laps: pd.DataFrame) -> pd.DataFrame:
    out = laps.copy()
    for column in ("season", "round", "lap_number", "stint", "position"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    for column in ("lap_start_sec", "lap_time_sec", "tyre_life"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out = out.dropna(
        subset=[
            *_DRIVER_KEYS,
            "lap_number",
            "stint",
            "lap_start_sec",
            "lap_time_sec",
        ]
    )
    out = out.loc[out["lap_time_sec"].gt(0)].copy()
    out["is_fresh_tyre"] = out["is_fresh_tyre"].fillna(False).astype(bool)
    out = out.sort_values([*_DRIVER_KEYS, "lap_number"]).drop_duplicates(
        [*_DRIVER_KEYS, "lap_number"], keep="last"
    )
    out["lap_end_sec"] = out["lap_start_sec"] + out["lap_time_sec"]
    return out.reset_index(drop=True)


def _derive_stops(laps: pd.DataFrame) -> pd.DataFrame:
    out = laps.copy()
    grouped = out.groupby(_DRIVER_KEYS, sort=False)
    out["previous_stint"] = grouped["stint"].shift()
    out["previous_lap"] = grouped["lap_number"].shift()
    out["old_compound"] = grouped["compound"].shift()
    transitions = out.loc[
        out["stint"].gt(out["previous_stint"]) & out["lap_number"].eq(out["previous_lap"] + 1)
    ].copy()
    if transitions.empty:
        return pd.DataFrame(
            columns=[
                *_DRIVER_KEYS,
                "race_name",
                "driver_name",
                "team",
                "stop_number",
                "pit_lap",
                "old_compound",
                "new_compound",
                "new_tyre_fresh",
            ]
        )
    transitions["stop_number"] = transitions.groupby(_DRIVER_KEYS).cumcount() + 1
    transitions["pit_lap"] = transitions["lap_number"] - 1
    transitions = transitions.rename(
        columns={"compound": "new_compound", "is_fresh_tyre": "new_tyre_fresh"}
    )
    return transitions.loc[
        :,
        [
            *_DRIVER_KEYS,
            "race_name",
            "driver_name",
            "team",
            "stop_number",
            "pit_lap",
            "old_compound",
            "new_compound",
            "new_tyre_fresh",
        ],
    ]


def _attach_durations(events: pd.DataFrame, stops: pd.DataFrame | None) -> pd.DataFrame:
    out = events.copy()
    if stops is None or stops.empty:
        out["duration_sec"] = np.nan
        return out
    _require_columns(stops, _STOP_REQUIRED, "stops")
    duration = stops.loc[:, [*_DRIVER_KEYS, "pit_lap", "duration_sec"]].copy()
    for column in ("season", "round", "pit_lap", "duration_sec"):
        duration[column] = pd.to_numeric(duration[column], errors="coerce")
    duration = duration.dropna(subset=[*_DRIVER_KEYS, "pit_lap"]).drop_duplicates(
        [*_DRIVER_KEYS, "pit_lap"], keep="last"
    )
    return out.merge(
        duration,
        on=[*_DRIVER_KEYS, "pit_lap"],
        how="left",
        validate="one_to_one",
    )


def _window_laps(
    race_laps: pd.DataFrame,
    early_code: str,
    late_code: str,
    before_lap: int,
    after_lap: int,
) -> pd.DataFrame:
    return race_laps.loc[
        race_laps["driver_code"].isin([early_code, late_code])
        & race_laps["lap_number"].between(before_lap, after_lap)
    ]


def _outcome_label(
    gap_before: float,
    gain: float,
    position_flip: bool,
    threshold: float,
) -> str:
    early_was_behind = gap_before > 0
    if position_flip:
        return "Undercut completed" if early_was_behind else "Overcut completed"
    if gain >= threshold:
        return "Early stop gained"
    if gain <= -threshold:
        return "Late stop gained"
    return "Position held"


def _confidence(
    gap_before: float,
    position_distance: int,
    separation: int,
    has_stop_timing: bool,
    same_new_compound: bool,
    fresh_new_tyres: bool,
) -> str:
    if (
        abs(gap_before) <= 3
        and position_distance == 1
        and separation <= 2
        and has_stop_timing
        and same_new_compound
        and fresh_new_tyres
    ):
        return "high"
    if abs(gap_before) <= 5 and position_distance == 1 and separation <= 3:
        return "medium"
    return "low"


def analyse_pit_windows(
    laps: pd.DataFrame,
    stops: pd.DataFrame | None = None,
    *,
    max_stop_separation_laps: int = MAX_STOP_SEPARATION_LAPS,
    max_pre_gap_sec: float = MAX_PRE_GAP_SEC,
    max_position_distance: int = MAX_POSITION_DISTANCE,
    outcome_threshold_sec: float = OUTCOME_THRESHOLD_SEC,
) -> pd.DataFrame:
    """Return one evidence row for every nearby pair of staggered stops.

    Positive ``net_time_gain_sec`` means the earlier-stopping driver improved
    their signed gap over the cycle.  ``on_track_gain_sec`` removes the observed
    stationary-time difference, but still includes tyre warm-up, traffic and
    driver pace; neither value is a causal strategy estimate.
    """
    _require_columns(laps, _LAP_REQUIRED, "laps")
    if max_stop_separation_laps < 1:
        raise ValueError("max_stop_separation_laps must be at least 1")
    if max_pre_gap_sec <= 0 or max_position_distance < 1 or outcome_threshold_sec < 0:
        raise ValueError("gap, position and outcome thresholds must be positive")
    if laps.empty:
        return _empty_result()

    pace = _prepare_laps(laps)
    events = _attach_durations(_derive_stops(pace), stops)
    if events.empty:
        return _empty_result()

    rows: list[dict[str, object]] = []
    for race_key, race_events in events.groupby(_RACE_KEYS, sort=True):
        race_laps = pace.loc[pace["season"].eq(race_key[0]) & pace["round"].eq(race_key[1])]
        lap_lookup = race_laps.set_index(["driver_code", "lap_number"])
        for first, second in combinations(race_events.to_dict("records"), 2):
            if first["driver_code"] == second["driver_code"]:
                continue
            if first["stop_number"] != second["stop_number"]:
                continue
            if first["pit_lap"] == second["pit_lap"]:
                continue
            early, late = (
                (first, second) if first["pit_lap"] < second["pit_lap"] else (second, first)
            )
            separation = int(late["pit_lap"] - early["pit_lap"])
            if separation > max_stop_separation_laps:
                continue
            before_lap = int(early["pit_lap"] - 1)
            after_lap = int(late["pit_lap"] + 1)
            keys = [
                (early["driver_code"], before_lap),
                (late["driver_code"], before_lap),
                (early["driver_code"], after_lap),
                (late["driver_code"], after_lap),
            ]
            if any(key not in lap_lookup.index for key in keys):
                continue
            early_before, late_before, early_after, late_after = [
                lap_lookup.loc[key] for key in keys
            ]
            timing = [
                early_before["lap_end_sec"],
                late_before["lap_end_sec"],
                early_after["lap_end_sec"],
                late_after["lap_end_sec"],
            ]
            positions = [
                early_before["position"],
                late_before["position"],
                early_after["position"],
                late_after["position"],
            ]
            if any(pd.isna(value) for value in [*timing, *positions]):
                continue
            gap_before = float(timing[0] - timing[1])
            if abs(gap_before) > max_pre_gap_sec:
                continue
            position_distance = int(abs(positions[0] - positions[1]))
            if position_distance > max_position_distance:
                continue

            window = _window_laps(
                race_laps,
                str(early["driver_code"]),
                str(late["driver_code"]),
                before_lap,
                after_lap,
            )
            expected_laps = 2 * (after_lap - before_lap + 1)
            window_complete = len(window) == expected_laps
            window_green = window_complete and window["track_status"].astype(str).eq("1").all()
            pair_events = race_events.loc[
                race_events["driver_code"].isin([early["driver_code"], late["driver_code"]])
                & race_events["pit_lap"].between(early["pit_lap"], after_lap)
            ]
            single_stop_each = pair_events.groupby("driver_code").size().eq(1).all()
            if not window_complete:
                exclusion_reason = "Incomplete timing window"
            elif not window_green:
                exclusion_reason = "Race-control affected"
            elif not single_stop_each:
                exclusion_reason = "Additional stop in window"
            else:
                exclusion_reason = None
            eligible = exclusion_reason is None

            gap_after = float(timing[2] - timing[3])
            gain = gap_before - gap_after
            early_duration = (
                float(early["duration_sec"]) if pd.notna(early["duration_sec"]) else np.nan
            )
            late_duration = (
                float(late["duration_sec"]) if pd.notna(late["duration_sec"]) else np.nan
            )
            has_stop_timing = not (np.isnan(early_duration) or np.isnan(late_duration))
            stop_delta = early_duration - late_duration if has_stop_timing else np.nan
            on_track_gain = gain + stop_delta if has_stop_timing else np.nan
            before_relation = int(np.sign(positions[1] - positions[0]))
            after_relation = int(np.sign(positions[3] - positions[2]))
            position_flip = before_relation != after_relation
            same_new_compound = early["new_compound"] == late["new_compound"]
            fresh_new_tyres = bool(early["new_tyre_fresh"]) and bool(late["new_tyre_fresh"])

            rows.append(
                {
                    "season": int(race_key[0]),
                    "round": int(race_key[1]),
                    "race_name": early["race_name"],
                    "stop_number": int(early["stop_number"]),
                    "early_driver_code": early["driver_code"],
                    "early_driver_name": early["driver_name"],
                    "early_team": early["team"],
                    "late_driver_code": late["driver_code"],
                    "late_driver_name": late["driver_name"],
                    "late_team": late["team"],
                    "early_pit_lap": int(early["pit_lap"]),
                    "late_pit_lap": int(late["pit_lap"]),
                    "stop_separation_laps": separation,
                    "checkpoint_before_lap": before_lap,
                    "checkpoint_after_lap": after_lap,
                    "early_old_compound": early["old_compound"],
                    "early_new_compound": early["new_compound"],
                    "late_old_compound": late["old_compound"],
                    "late_new_compound": late["new_compound"],
                    "early_new_tyre_fresh": bool(early["new_tyre_fresh"]),
                    "late_new_tyre_fresh": bool(late["new_tyre_fresh"]),
                    "position_before_early": int(positions[0]),
                    "position_before_late": int(positions[1]),
                    "position_after_early": int(positions[2]),
                    "position_after_late": int(positions[3]),
                    "gap_before_sec": gap_before,
                    "gap_after_sec": gap_after,
                    "net_time_gain_sec": gain if eligible else np.nan,
                    "early_stop_duration_sec": early_duration,
                    "late_stop_duration_sec": late_duration,
                    "stop_duration_delta_sec": stop_delta,
                    "on_track_gain_sec": on_track_gain if eligible else np.nan,
                    "position_flip": position_flip,
                    "window_green": bool(window_green),
                    "eligible": eligible,
                    "exclusion_reason": exclusion_reason,
                    "confidence": (
                        _confidence(
                            gap_before,
                            position_distance,
                            separation,
                            has_stop_timing,
                            same_new_compound,
                            fresh_new_tyres,
                        )
                        if eligible
                        else "excluded"
                    ),
                    "opportunity_type": (
                        "Undercut opportunity" if gap_before > 0 else "Overcut opportunity"
                    ),
                    "outcome_label": (
                        _outcome_label(
                            gap_before,
                            gain,
                            position_flip,
                            outcome_threshold_sec,
                        )
                        if eligible
                        else "Excluded"
                    ),
                    "methodology_version": "pit-window-v1",
                }
            )
    if not rows:
        return _empty_result()
    return (
        pd.DataFrame(rows, columns=PIT_WINDOW_COLUMNS)
        .sort_values(["season", "round", "early_pit_lap", "early_driver_code", "late_driver_code"])
        .reset_index(drop=True)
    )
