"""Observed position and relative-gap changes across race neutralisations.

Official Safety Car, VSC and red-flag messages are paired with a small state
machine. Driver state at deployment is compared with the third leader crossing
after the end signal. Publication requires two complete green reference-leader
laps, not a claim that every driver's recovery is independently observed.
The metric is descriptive evidence, not a causal strategy estimate.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

METHODOLOGY_VERSION = "race-control-impact-v3"
MAX_CAPTURE_OFFSET_S = 3.0
HIGH_CONFIDENCE_OFFSET_S = 1.5
MAX_INTERPOLATION_SPAN_S = 2.0
DEFAULT_MIN_EVENT_DRIVERS = 12
MIN_TIME_COMPARABLE_DRIVERS = 5
MIN_PIT_REFERENCE_STOPS = 5
MIN_PIT_REFERENCE_DRIVERS = 4
HIGH_PIT_REFERENCE_STOPS = 8
HIGH_PIT_REFERENCE_DRIVERS = 5
MAX_PIT_REFERENCE_MAD_S = 2.0
HIGH_PIT_REFERENCE_MAD_S = 1.0
PIT_BOOTSTRAP_SAMPLES = 1_000
TIMING_RESOLUTION_S = 1.0
# Reconstructed progress is not official lapping evidence. Suppress estimates
# close to a whole-lap boundary rather than converting interpolation noise to a lap.
LAP_DEFICIT_BOUNDARY_MARGIN = 0.02

_RACE_KEYS = ["season", "round"]
_REPLAY_REQUIRED = {
    *_RACE_KEYS,
    "race_name",
    "driver_code",
    "driver_name",
    "team",
    "t_s",
    "lap_number",
    "lap_progress",
    "stint",
    "compound",
    "tyre_life",
    "running_order",
    "gap_to_leader_s",
}
_REPLAY_PROVENANCE_DEFAULTS: dict[str, object] = {
    "running_order_source": "lap_progress_estimate",
    "running_order_confidence": "Medium",
    "running_order_observed_t_s": np.nan,
    "gap_source": "lap_progress_estimate",
    "gap_confidence": "Medium",
    "gap_observed_t_s": np.nan,
}
_TRUSTED_REPLAY_SOURCES = {"openf1_recorded", "lap_progress_estimate"}
_CONTROL_REQUIRED = {
    *_RACE_KEYS,
    "race_name",
    "t_s",
    "category",
    "flag",
    "message",
    "lap",
}
_LAPS_REQUIRED = {
    *_RACE_KEYS,
    "driver_code",
    "lap_number",
    "track_status",
    "lap_start_t_s",
    "lap_end_t_s",
}
_STOPS_REQUIRED = {*_RACE_KEYS, "driver_code", "pit_lap", "duration_sec"}

RACE_CONTROL_EVENT_COLUMNS = [
    "season",
    "round",
    "race_name",
    "event_id",
    "event_number",
    "event_type",
    "start_t_s",
    "end_t_s",
    "post_checkpoint_t_s",
    "deployment_lap",
    "end_lap",
    "post_checkpoint_lap",
    "duration_s",
    "event_status",
    "recovery_clean",
    "pre_driver_count",
    "post_driver_count",
    "eligible_driver_count",
    "time_comparable_driver_count",
    "time_eligible",
    "time_exclusion_reason",
    "intervention_stop_count",
    "recovery_stop_count",
    "position_gainer_count",
    "position_loser_count",
    "position_status",
    "gap_status",
    "pit_status",
    "restart_status",
    "tyre_status",
    "focus_driver_code",
    "eligible",
    "exclusion_reason",
    "confidence",
    "methodology_version",
]

RACE_CONTROL_IMPACT_COLUMNS = [
    "season",
    "round",
    "race_name",
    "event_id",
    "event_number",
    "event_type",
    "driver_code",
    "driver_name",
    "team",
    "position_before",
    "position_after",
    "positions_gained",
    "position_before_source",
    "position_after_source",
    "position_before_confidence",
    "position_after_confidence",
    "position_before_observed_t_s",
    "position_after_observed_t_s",
    "position_evidence_class",
    "gap_to_leader_before_s",
    "gap_to_leader_after_s",
    "raw_gap_gain_s",
    "field_adjusted_gap_gain_s",
    "gap_before_source",
    "gap_after_source",
    "gap_before_confidence",
    "gap_after_confidence",
    "gap_before_observed_t_s",
    "gap_after_observed_t_s",
    "gap_evidence_class",
    "time_comparable_driver_count",
    "time_eligible",
    "time_exclusion_reason",
    "lap_before",
    "lap_after",
    "lap_deficit_before",
    "lap_deficit_after",
    "lap_deficit_changed",
    "stint_before",
    "stint_after",
    "compound_before",
    "compound_after",
    "tyre_life_before",
    "tyre_life_after",
    "pitted_during_intervention",
    "pitted_during_recovery",
    "pit_timing_class",
    "pit_in_t_s",
    "pit_out_t_s",
    "pit_duration_sec",
    "stop_count",
    "tyre_changed_during_suspension",
    "active_after",
    "position_eligible",
    "gap_eligible",
    "pit_eligible",
    "restart_eligible",
    "tyre_eligible",
    "story_status",
    "story_direction",
    "story_reason",
    "material_effect_count",
    "evaluated_effect_count",
    "focus_rank",
    "eligible",
    "exclusion_reason",
    "confidence",
    "outcome_label",
    "timing_before_offset_s",
    "timing_after_offset_s",
    "methodology_version",
]

RACE_CONTROL_CHECKPOINT_COLUMNS = [
    "season",
    "round",
    "race_name",
    "event_id",
    "event_number",
    "event_type",
    "driver_code",
    "driver_name",
    "team",
    "checkpoint_type",
    "checkpoint_order",
    "checkpoint_t_s",
    "lap_number",
    "lap_progress",
    "running_order",
    "gap_to_leader_s",
    "running_order_source",
    "running_order_confidence",
    "running_order_observed_t_s",
    "gap_source",
    "gap_confidence",
    "gap_observed_t_s",
    "evidence_class",
    "stint",
    "compound",
    "tyre_life",
    "capture_offset_s",
    "source",
    "eligible",
    "exclusion_reason",
    "methodology_version",
]

RACE_CONTROL_EFFECT_COLUMNS = [
    "season",
    "round",
    "race_name",
    "event_id",
    "event_number",
    "event_type",
    "driver_code",
    "effect_type",
    "effect_scope",
    "value",
    "lower_bound",
    "upper_bound",
    "unit",
    "evidence_class",
    "confidence",
    "sample_size",
    "eligible",
    "exclusion_reason",
    "methodology_version",
]

_EVENT_INTEGER = {
    "season",
    "round",
    "event_number",
    "deployment_lap",
    "end_lap",
    "post_checkpoint_lap",
    "pre_driver_count",
    "post_driver_count",
    "eligible_driver_count",
    "time_comparable_driver_count",
    "intervention_stop_count",
    "recovery_stop_count",
    "position_gainer_count",
    "position_loser_count",
}
_EVENT_FLOAT = {"start_t_s", "end_t_s", "post_checkpoint_t_s", "duration_s"}
_EVENT_BOOLEAN = {"recovery_clean", "eligible", "time_eligible"}
_IMPACT_INTEGER = {
    "season",
    "round",
    "event_number",
    "position_before",
    "position_after",
    "positions_gained",
    "lap_before",
    "lap_after",
    "lap_deficit_before",
    "lap_deficit_after",
    "stint_before",
    "stint_after",
    "tyre_life_before",
    "tyre_life_after",
    "stop_count",
    "time_comparable_driver_count",
    "material_effect_count",
    "evaluated_effect_count",
    "focus_rank",
}
_IMPACT_FLOAT = {
    "gap_to_leader_before_s",
    "gap_to_leader_after_s",
    "raw_gap_gain_s",
    "field_adjusted_gap_gain_s",
    "timing_before_offset_s",
    "timing_after_offset_s",
    "position_before_observed_t_s",
    "position_after_observed_t_s",
    "gap_before_observed_t_s",
    "gap_after_observed_t_s",
    "pit_in_t_s",
    "pit_out_t_s",
    "pit_duration_sec",
}
_IMPACT_BOOLEAN = {
    "lap_deficit_changed",
    "pitted_during_intervention",
    "pitted_during_recovery",
    "tyre_changed_during_suspension",
    "active_after",
    "position_eligible",
    "gap_eligible",
    "pit_eligible",
    "restart_eligible",
    "tyre_eligible",
    "eligible",
    "time_eligible",
}

_CHECKPOINT_INTEGER = {
    "season",
    "round",
    "event_number",
    "checkpoint_order",
    "lap_number",
    "running_order",
    "stint",
    "tyre_life",
}
_CHECKPOINT_FLOAT = {
    "checkpoint_t_s",
    "lap_progress",
    "gap_to_leader_s",
    "capture_offset_s",
    "running_order_observed_t_s",
    "gap_observed_t_s",
}
_CHECKPOINT_BOOLEAN = {"eligible"}
_EFFECT_INTEGER = {"season", "round", "event_number", "sample_size"}
_EFFECT_FLOAT = {"value", "lower_bound", "upper_bound"}
_EFFECT_BOOLEAN = {"eligible"}


@dataclass(frozen=True)
class RaceControlImpactResult:
    """Event-level summary and driver-level supporting evidence."""

    events: pd.DataFrame
    evidence: pd.DataFrame
    checkpoints: pd.DataFrame = field(default_factory=pd.DataFrame)
    effects: pd.DataFrame = field(default_factory=pd.DataFrame)


@dataclass(frozen=True)
class _Event:
    event_number: int
    event_type: str
    start_t_s: float
    start_lap: int | None
    end_t_s: float | None
    end_lap: int | None
    status: str
    parse_reason: str | None = None


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


def _empty_result() -> RaceControlImpactResult:
    return RaceControlImpactResult(
        events=_typed_empty(
            RACE_CONTROL_EVENT_COLUMNS, _EVENT_INTEGER, _EVENT_FLOAT, _EVENT_BOOLEAN
        ),
        evidence=_typed_empty(
            RACE_CONTROL_IMPACT_COLUMNS, _IMPACT_INTEGER, _IMPACT_FLOAT, _IMPACT_BOOLEAN
        ),
        checkpoints=_typed_empty(
            RACE_CONTROL_CHECKPOINT_COLUMNS,
            _CHECKPOINT_INTEGER,
            _CHECKPOINT_FLOAT,
            _CHECKPOINT_BOOLEAN,
        ),
        effects=_typed_empty(
            RACE_CONTROL_EFFECT_COLUMNS, _EFFECT_INTEGER, _EFFECT_FLOAT, _EFFECT_BOOLEAN
        ),
    )


def _require_columns(frame: pd.DataFrame, required: set[str], name: str) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{name} is missing columns: {sorted(missing)}")


def _normalise(value: object) -> str:
    return " ".join(str(value).upper().split())


def _source_value(value: object) -> str:
    return "" if pd.isna(value) else str(value)


def _evidence_class(before_source: object, after_source: object) -> str:
    """Classify a pair conservatively by its weakest timing source."""
    sources = {_source_value(before_source), _source_value(after_source)}
    if "" in sources or not sources.issubset(_TRUSTED_REPLAY_SOURCES):
        return "unavailable"
    return "recorded" if sources == {"openf1_recorded"} else "estimated"


def _marker(message: str, flag: str) -> tuple[str, str] | None:
    if message in {"VSC DEPLOYED", "VIRTUAL SAFETY CAR DEPLOYED"}:
        return "VSC", "start"
    if message in {"VSC ENDING", "VIRTUAL SAFETY CAR ENDING"}:
        return "VSC", "end"
    if message == "SAFETY CAR DEPLOYED":
        return "Safety Car", "start"
    if message == "SAFETY CAR IN THIS LAP":
        return "Safety Car", "end"
    if flag == "RED" or message == "RED FLAG" or message.startswith("RED FLAG - RACE SUSPENDED"):
        return "Red Flag", "start"
    if message in {"STANDING START", "ROLLING START"}:
        return "Red Flag", "end"
    return None


def _optional_int(value: object) -> int | None:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return int(numeric) if pd.notna(numeric) else None


def _extract_events(control: pd.DataFrame) -> list[_Event]:
    events: list[_Event] = []
    opened: dict[str, tuple[float, int | None]] = {}
    for row in control.sort_values("t_s").itertuples(index=False):
        message = _normalise(row.message)
        flag = _normalise(row.flag)
        t_s, lap = float(row.t_s), _optional_int(row.lap)
        if flag == "CHEQUERED" or message == "CHEQUERED FLAG":
            for event_type in ("Safety Car", "VSC"):
                started = opened.pop(event_type, None)
                if started is not None and t_s > started[0]:
                    events.append(
                        _Event(
                            0,
                            event_type,
                            started[0],
                            started[1],
                            t_s,
                            lap,
                            "finished",
                            f"Race finished under {event_type}",
                        )
                    )
            continue
        marker = _marker(message, flag)
        if marker is None:
            continue
        event_type, action = marker
        if action == "start":
            if event_type == "Red Flag":
                for interrupted_type in ("Safety Car", "VSC"):
                    interrupted = opened.pop(interrupted_type, None)
                    if interrupted is not None:
                        events.append(
                            _Event(
                                0,
                                interrupted_type,
                                interrupted[0],
                                interrupted[1],
                                t_s,
                                lap,
                                "interrupted",
                                "Interrupted by red flag",
                            )
                        )
            elif event_type in {"Safety Car", "VSC"}:
                interrupted_type = "VSC" if event_type == "Safety Car" else "Safety Car"
                interrupted = opened.pop(interrupted_type, None)
                if interrupted is not None:
                    events.append(
                        _Event(
                            0,
                            interrupted_type,
                            interrupted[0],
                            interrupted[1],
                            t_s,
                            lap,
                            "interrupted",
                            f"Superseded by {event_type}",
                        )
                    )
            previous = opened.get(event_type)
            if previous is not None:
                events.append(
                    _Event(
                        0,
                        event_type,
                        previous[0],
                        previous[1],
                        t_s,
                        lap,
                        "interrupted",
                        "Superseded by another deployment",
                    )
                )
            opened[event_type] = (t_s, lap)
            continue
        started = opened.pop(event_type, None)
        if started is not None and t_s > started[0]:
            events.append(_Event(0, event_type, started[0], started[1], t_s, lap, "complete"))
    for event_type, (start_t_s, start_lap) in opened.items():
        events.append(
            _Event(
                0,
                event_type,
                start_t_s,
                start_lap,
                None,
                None,
                "unclosed",
                "No matching end message",
            )
        )
    ordered = sorted(events, key=lambda event: event.start_t_s)
    return [replace(event, event_number=index) for index, event in enumerate(ordered, start=1)]


def _event_id(season: int, rnd: int, event: _Event) -> str:
    slug = {"Safety Car": "sc", "VSC": "vsc", "Red Flag": "red"}[event.event_type]
    return f"{season}-{rnd:02d}-{slug}-{event.event_number:02d}"


def _snapshot(frame: pd.DataFrame, target_t_s: float, *, before: bool) -> pd.DataFrame:
    mask = frame["t_s"].le(target_t_s) if before else frame["t_s"].ge(target_t_s)
    candidates = frame.loc[mask].sort_values(["driver_code", "t_s"])
    if candidates.empty:
        return candidates
    snapshot = (
        candidates.groupby("driver_code", sort=False).tail(1)
        if before
        else candidates.groupby("driver_code", sort=False).head(1)
    ).copy()
    snapshot["capture_offset_s"] = (
        target_t_s - snapshot["t_s"] if before else snapshot["t_s"] - target_t_s
    )
    snapshot = snapshot.loc[snapshot["capture_offset_s"].le(MAX_CAPTURE_OFFSET_S)].copy()
    ranks = pd.to_numeric(snapshot["running_order"], errors="coerce")
    coherent = (
        len(snapshot) > 0
        and ranks.notna().all()
        and ranks.is_unique
        and sorted(ranks.astype(int).tolist()) == list(range(1, len(snapshot) + 1))
    )
    if not coherent:
        snapshot["running_order"] = np.nan
        snapshot["running_order_source"] = ""
        snapshot["running_order_confidence"] = ""
        snapshot["running_order_observed_t_s"] = np.nan
    return snapshot


def _invalidate_incoherent_checkpoint_orders(rows: list[dict[str, object]]) -> None:
    """Fail closed when separately captured drivers do not form one dense field."""
    grouped: dict[tuple[str, int], list[dict[str, object]]] = {}
    for row in rows:
        if str(row["checkpoint_type"]) in {"pit_in", "pit_out"}:
            continue
        grouped.setdefault(
            (str(row["checkpoint_type"]), int(str(row["checkpoint_order"]))), []
        ).append(row)
    for checkpoint_rows in grouped.values():
        eligible = [row for row in checkpoint_rows if bool(row["eligible"])]
        ranks = [_to_int(row.get("running_order")) for row in eligible]
        coherent = (
            len(eligible) == len(checkpoint_rows)
            and all(rank is not None for rank in ranks)
            and len(set(ranks)) == len(ranks)
            and sorted(int(rank) for rank in ranks if rank is not None)
            == list(range(1, len(ranks) + 1))
        )
        if coherent:
            continue
        for row in checkpoint_rows:
            row["eligible"] = False
            row["evidence_class"] = "unavailable"
            row["exclusion_reason"] = "Checkpoint order is not a coherent dense field"


def _interpolated_state(frame: pd.DataFrame, target_t_s: float) -> dict[str, object] | None:
    """Interpolate one driver's replay state without hiding timing resolution."""
    if frame.empty or "t_s" not in frame:
        return None
    ordered = frame.dropna(subset=["t_s"])
    if ordered.empty:
        return None
    if not ordered["t_s"].is_monotonic_increasing:
        ordered = ordered.sort_values("t_s")
    ordered = ordered.drop_duplicates("t_s")
    times = ordered["t_s"].to_numpy(dtype=float)
    right_index = int(np.searchsorted(times, target_t_s, side="left"))
    if right_index == len(times):
        return None
    if times[right_index] == target_t_s:
        left_index = right_index
    elif right_index == 0:
        return None
    else:
        left_index = right_index - 1
    left, right = ordered.iloc[left_index], ordered.iloc[right_index]
    left_t, right_t = float(left["t_s"]), float(right["t_s"])
    span = right_t - left_t
    if span > MAX_INTERPOLATION_SPAN_S:
        return None
    weight = 0.0 if span <= 0 else (target_t_s - left_t) / span
    state: dict[str, object] = dict(left.to_dict())
    for column in ("lap_progress", "gap_to_leader_s"):
        left_value = pd.to_numeric(pd.Series([left.get(column)]), errors="coerce").iloc[0]
        right_value = pd.to_numeric(pd.Series([right.get(column)]), errors="coerce").iloc[0]
        state[column] = (
            float(left_value + weight * (right_value - left_value))
            if pd.notna(left_value) and pd.notna(right_value)
            else np.nan
        )
    state["t_s"] = target_t_s
    state["capture_offset_s"] = max(target_t_s - left_t, right_t - target_t_s)
    return state


def _prepare_stops(stops: pd.DataFrame | None) -> pd.DataFrame:
    if stops is None or stops.empty:
        return pd.DataFrame(columns=sorted(_STOPS_REQUIRED))
    _require_columns(stops, _STOPS_REQUIRED, "stops")
    out = stops.copy()
    for column in ("season", "round", "pit_lap", "duration_sec"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    return out.dropna(subset=["season", "round", "driver_code", "pit_lap"])


def _pit_transitions(laps: pd.DataFrame, stops: pd.DataFrame | None) -> pd.DataFrame:
    columns = [
        "season",
        "round",
        "driver_code",
        "pit_lap",
        "pit_in_t_s",
        "pit_out_t_s",
        "duration_sec",
        "old_compound",
        "new_compound",
    ]
    if laps.empty or "pit_in_t_s" not in laps or "pit_out_t_s" not in laps:
        return pd.DataFrame(columns=columns)
    official = _prepare_stops(stops)
    rows: list[dict[str, object]] = []
    ordered = laps.sort_values([*_RACE_KEYS, "driver_code", "lap_number"])
    for keys, driver_laps in ordered.groupby([*_RACE_KEYS, "driver_code"], sort=False):
        driver_laps = driver_laps.reset_index(drop=True)
        for _index, lap in driver_laps.loc[driver_laps["pit_in_t_s"].notna()].iterrows():
            following = driver_laps.loc[
                driver_laps["lap_number"].between(lap["lap_number"], lap["lap_number"] + 2)
                & driver_laps["pit_out_t_s"].notna()
                & driver_laps["pit_out_t_s"].gt(lap["pit_in_t_s"])
            ].head(1)
            if following.empty:
                continue
            out_lap = following.iloc[0]
            match = official.loc[
                official["season"].eq(keys[0])
                & official["round"].eq(keys[1])
                & official["driver_code"].eq(keys[2])
                & official["pit_lap"].eq(lap["lap_number"])
            ]
            measured = float(out_lap["pit_out_t_s"] - lap["pit_in_t_s"])
            duration = float(match.iloc[0]["duration_sec"]) if not match.empty else measured
            next_compound = out_lap.get("compound", "")
            rows.append(
                {
                    "season": int(keys[0]),
                    "round": int(keys[1]),
                    "driver_code": str(keys[2]),
                    "pit_lap": int(lap["lap_number"]),
                    "pit_in_t_s": float(lap["pit_in_t_s"]),
                    "pit_out_t_s": float(out_lap["pit_out_t_s"]),
                    "duration_sec": duration,
                    "old_compound": str(lap.get("compound", "")),
                    "new_compound": str(next_compound) if pd.notna(next_compound) else "",
                }
            )
    return pd.DataFrame(rows, columns=columns)


def _pit_classification(transition: pd.Series, event: _Event, post_t_s: float | None) -> str:
    pit_in = float(transition["pit_in_t_s"])
    if pit_in < event.start_t_s:
        return "before_deployment"
    if event.end_t_s is not None and pit_in <= event.end_t_s:
        return "during_neutralisation"
    if event.end_t_s is not None and (post_t_s is None or pit_in <= post_t_s):
        return "after_end"
    return "outside_event_window"


def _checkpoint_row(
    replay_race: pd.DataFrame,
    event: _Event,
    event_key: str,
    race_name: str,
    driver_code: str,
    checkpoint_type: str,
    checkpoint_order: int,
    checkpoint_t_s: float,
    *,
    source: str,
) -> dict[str, object]:
    driver = replay_race.loc[replay_race["driver_code"].eq(driver_code)]
    state = _interpolated_state(driver, checkpoint_t_s)
    position_source = _source_value(state.get("running_order_source")) if state else ""
    eligible = state is not None and position_source in _TRUSTED_REPLAY_SOURCES
    reason = ""
    if state is None:
        reason = "Replay does not bracket checkpoint within 2 seconds"
    elif not eligible:
        reason = "Position provenance unavailable at checkpoint"
    state = state or {}
    evidence_class = (
        "recorded"
        if position_source == "openf1_recorded"
        else "estimated"
        if eligible
        else "unavailable"
    )
    return {
        "season": int(replay_race["season"].iloc[0]),
        "round": int(replay_race["round"].iloc[0]),
        "race_name": race_name,
        "event_id": event_key,
        "event_number": event.event_number,
        "event_type": event.event_type,
        "driver_code": driver_code,
        "driver_name": str(state.get("driver_name", driver_code)),
        "team": str(state.get("team", "")),
        "checkpoint_type": checkpoint_type,
        "checkpoint_order": checkpoint_order,
        "checkpoint_t_s": checkpoint_t_s,
        "lap_number": _to_int(state.get("lap_number")),
        "lap_progress": state.get("lap_progress", np.nan),
        "running_order": _to_int(state.get("running_order")),
        "gap_to_leader_s": state.get("gap_to_leader_s", np.nan),
        "running_order_source": position_source,
        "running_order_confidence": _source_value(state.get("running_order_confidence")),
        "running_order_observed_t_s": state.get("running_order_observed_t_s", np.nan),
        "gap_source": _source_value(state.get("gap_source")),
        "gap_confidence": _source_value(state.get("gap_confidence")),
        "gap_observed_t_s": state.get("gap_observed_t_s", np.nan),
        "evidence_class": evidence_class,
        "stint": _to_int(state.get("stint")),
        "compound": str(state.get("compound", "")),
        "tyre_life": _to_int(state.get("tyre_life")),
        "capture_offset_s": state.get("capture_offset_s", np.nan),
        "source": source,
        "eligible": eligible,
        "exclusion_reason": reason,
        "methodology_version": METHODOLOGY_VERSION,
    }


def _green_one_checkpoint(replay: pd.DataFrame, event: _Event) -> float | None:
    if event.end_t_s is None:
        return None
    leader_at_end = replay.loc[
        replay["t_s"].le(event.end_t_s) & replay["running_order"].eq(1)
    ].sort_values("t_s")
    if leader_at_end.empty:
        return None
    end_lap = _optional_int(leader_at_end.iloc[-1]["lap_number"])
    if end_lap is None:
        return None
    crossing = replay.loc[
        replay["t_s"].gt(event.end_t_s)
        & replay["running_order"].eq(1)
        & replay["lap_number"].ge(end_lap + 1)
    ]
    return None if crossing.empty else float(crossing["t_s"].min())


def _post_checkpoint(replay: pd.DataFrame, event: _Event) -> tuple[float, int] | None:
    if event.end_t_s is None:
        return None
    leader_at_end = replay.loc[
        replay["t_s"].le(event.end_t_s) & replay["running_order"].eq(1)
    ].sort_values("t_s")
    if leader_at_end.empty:
        return None
    if event.end_t_s - float(leader_at_end.iloc[-1]["t_s"]) > MAX_CAPTURE_OFFSET_S:
        return None
    end_lap = _optional_int(leader_at_end.iloc[-1]["lap_number"])
    if end_lap is None:
        return None
    post_lap = end_lap + 3
    crossing = replay.loc[
        replay["t_s"].gt(event.end_t_s)
        & replay["running_order"].eq(1)
        & replay["lap_number"].ge(post_lap)
    ]
    if crossing.empty:
        return None
    return float(crossing["t_s"].min()), post_lap


def _recovery_clean(
    laps: pd.DataFrame, replay: pd.DataFrame, event: _Event, checkpoint: tuple[float, int] | None
) -> bool:
    """Require timed, complete green laps, not same-number laps of lapped cars.

    The two complete reference-leader laps must be green. Other laps wholly
    inside the interval may contradict them; flags on straddling laps cannot be
    localised to this interval. This is not proof of full-field status coverage.
    """
    if checkpoint is None or event.end_t_s is None:
        return False
    end, post_lap = checkpoint
    first = replay.loc[
        replay["t_s"].gt(event.end_t_s)
        & replay["running_order"].eq(1)
        & replay["lap_number"].eq(post_lap - 2)
    ].sort_values("t_s")
    last = replay.loc[replay["t_s"].eq(end) & replay["running_order"].eq(1)]
    if first.empty or len(last) != 1:
        return False
    start = float(first.iloc[0]["t_s"])
    driver = first.iloc[0]["driver_code"]
    if start >= end or driver != last.iloc[0]["driver_code"]:
        return False
    reference = laps.loc[
        laps["driver_code"].eq(driver) & laps["lap_number"].isin([post_lap - 2, post_lap - 1])
    ].sort_values("lap_number")
    if len(reference) != 2 or reference["lap_number"].nunique() != 2:
        return False
    starts = reference["lap_start_t_s"].to_numpy(dtype=float)
    ends = reference["lap_end_t_s"].to_numpy(dtype=float)
    if not (np.isfinite(starts).all() and np.isfinite(ends).all() and (ends > starts).all()):
        return False
    # Replay samples the crossings; staged lap times provide the true interval.
    if not (
        starts[0] >= event.end_t_s
        and 0 <= start - starts[0] <= MAX_CAPTURE_OFFSET_S
        and 0 <= end - ends[1] <= MAX_CAPTURE_OFFSET_S
        and abs(ends[0] - starts[1]) <= 0.001
    ):
        return False
    if not reference["track_status"].astype("string").eq("1").fillna(False).all():
        return False
    # A later observed lap start bounds an earlier untimed lap; otherwise one
    # missing SC lap duration would poison every subsequent recovery in the race.
    coverage = laps.sort_values(["driver_code", "lap_number"]).copy()
    next_start = coverage.groupby("driver_code")["lap_start_t_s"].shift(-1)
    coverage_end = coverage["lap_end_t_s"].fillna(next_start)
    contained = coverage.loc[
        coverage["lap_start_t_s"].ge(starts[0])
        & coverage_end.le(ends[1])
        & coverage_end.gt(coverage["lap_start_t_s"])
    ]
    unknown = (
        coverage["lap_start_t_s"].ge(starts[0])
        & coverage["lap_start_t_s"].lt(ends[1])
        & (coverage_end.isna() | coverage_end.le(coverage["lap_start_t_s"]))
    )
    if unknown.any():
        return False
    return bool(
        not contained.empty
        and contained["track_status"].astype("string").eq("1").fillna(False).all()
    )


def _estimated_lap_deficits(snapshot: pd.DataFrame) -> dict[str, int | None]:
    leaders = snapshot.loc[snapshot["running_order"].eq(1)]
    if len(leaders) != 1:
        return {}
    leader = leaders.iloc[0]
    if pd.isna(leader["lap_number"]) or pd.isna(leader["lap_progress"]):
        return {}
    leader_progress = float(leader["lap_number"] - 1 + leader["lap_progress"])
    result: dict[str, int | None] = {}
    for row in snapshot.itertuples(index=False):
        if pd.isna(row.lap_number) or pd.isna(row.lap_progress):
            result[str(row.driver_code)] = None
            continue
        distance = leader_progress - float(row.lap_number - 1 + row.lap_progress)
        deficit = None
        if (
            np.isfinite(distance)
            and row.t_s == leader["t_s"]
            and 0 <= row.lap_progress <= 1
            and 0 <= leader["lap_progress"] <= 1
            and distance >= -0.0001
        ):
            distance = max(0.0, distance)
            nearest = round(distance)
            if nearest == 0 or abs(distance - nearest) > LAP_DEFICIT_BOUNDARY_MARGIN + 1e-9:
                deficit = int(np.floor(distance))
        result[str(row.driver_code)] = deficit
    return result


def _transition_overlaps(
    transitions: pd.DataFrame, driver_code: str, start_t_s: float, end_t_s: float
) -> bool:
    if transitions.empty:
        return False
    return bool(
        (
            transitions["driver_code"].eq(driver_code)
            & transitions["pit_in_t_s"].le(end_t_s)
            & transitions["pit_out_t_s"].ge(start_t_s)
        ).any()
    )


def _cached_state(
    replay_by_driver: dict[str, pd.DataFrame],
    cache: dict[tuple[str, float], dict[str, object] | None],
    driver_code: str,
    target_t_s: float,
) -> dict[str, object] | None:
    key = (driver_code, target_t_s)
    if key not in cache:
        cache[key] = _interpolated_state(
            replay_by_driver.get(driver_code, pd.DataFrame()), target_t_s
        )
    return cache[key]


def _replay_driver_frames(replay: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        str(code): frame.sort_values("t_s").reset_index(drop=True)
        for code, frame in replay.groupby("driver_code", sort=False)
    }


def _pairwise_pit_loss(
    replay: pd.DataFrame,
    transition: pd.Series,
    transitions: pd.DataFrame,
    *,
    replay_by_driver: dict[str, pd.DataFrame] | None = None,
    state_cache: dict[tuple[str, float], dict[str, object] | None] | None = None,
) -> tuple[float, int]:
    """Observed loss versus the median non-pitting same-lap peer."""
    driver = str(transition["driver_code"])
    start_t_s = float(transition["pit_in_t_s"])
    end_t_s = float(transition["pit_out_t_s"])
    replay_by_driver = replay_by_driver or _replay_driver_frames(replay)
    state_cache = state_cache if state_cache is not None else {}
    target_before = _cached_state(replay_by_driver, state_cache, driver, start_t_s)
    target_after = _cached_state(replay_by_driver, state_cache, driver, end_t_s)
    if target_before is None or target_after is None:
        return np.nan, 0
    target_gap_before = pd.to_numeric(
        pd.Series([target_before.get("gap_to_leader_s")]), errors="coerce"
    ).iloc[0]
    target_gap_after = pd.to_numeric(
        pd.Series([target_after.get("gap_to_leader_s")]), errors="coerce"
    ).iloc[0]
    if pd.isna(target_gap_before) or pd.isna(target_gap_after):
        return np.nan, 0
    changes: list[float] = []
    for peer in replay_by_driver:
        if peer == driver or _transition_overlaps(transitions, peer, start_t_s, end_t_s):
            continue
        peer_before = _cached_state(replay_by_driver, state_cache, peer, start_t_s)
        peer_after = _cached_state(replay_by_driver, state_cache, peer, end_t_s)
        if peer_before is None or peer_after is None:
            continue
        peer_gap_before = pd.to_numeric(
            pd.Series([peer_before.get("gap_to_leader_s")]), errors="coerce"
        ).iloc[0]
        peer_gap_after = pd.to_numeric(
            pd.Series([peer_after.get("gap_to_leader_s")]), errors="coerce"
        ).iloc[0]
        lap_values = [
            _to_int(target_before.get("lap_number")),
            _to_int(target_after.get("lap_number")),
            _to_int(peer_before.get("lap_number")),
            _to_int(peer_after.get("lap_number")),
        ]
        if (
            pd.isna(peer_gap_before)
            or pd.isna(peer_gap_after)
            or any(value is None for value in lap_values)
        ):
            continue
        target_lap_before, target_lap_after, peer_lap_before, peer_lap_after = (
            int(str(value)) for value in lap_values
        )
        if target_lap_before - peer_lap_before != target_lap_after - peer_lap_after:
            continue
        pair_before = float(target_gap_before - peer_gap_before)
        pair_after = float(target_gap_after - peer_gap_after)
        changes.append(pair_after - pair_before)
    return (float(np.median(changes)), len(changes)) if changes else (np.nan, 0)


def _green_reference_losses(
    replay: pd.DataFrame,
    laps: pd.DataFrame,
    transitions: pd.DataFrame,
    events: list[_Event],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    replay_by_driver = _replay_driver_frames(replay)
    state_cache: dict[tuple[str, float], dict[str, object] | None] = {}
    for _, transition in transitions.iterrows():
        start_t_s = float(transition["pit_in_t_s"])
        end_t_s = float(transition["pit_out_t_s"])
        overlaps_control = any(
            event.end_t_s is None or (start_t_s <= event.end_t_s and end_t_s >= event.start_t_s)
            for event in events
        )
        if overlaps_control:
            continue
        driver_laps = laps.loc[
            laps["driver_code"].eq(transition["driver_code"])
            & laps["lap_number"].between(transition["pit_lap"], transition["pit_lap"] + 1)
        ]
        if len(driver_laps) < 2 or not driver_laps["track_status"].astype(str).eq("1").all():
            continue
        loss, peer_count = _pairwise_pit_loss(
            replay,
            transition,
            transitions,
            replay_by_driver=replay_by_driver,
            state_cache=state_cache,
        )
        if not np.isfinite(loss) or peer_count < MIN_TIME_COMPARABLE_DRIVERS:
            continue
        rows.append(
            {
                "driver_code": str(transition["driver_code"]),
                "duration_sec": float(transition["duration_sec"]),
                "observed_loss_sec": loss,
                "peer_count": peer_count,
            }
        )
    return pd.DataFrame(rows)


def _pit_effect_rows(
    replay: pd.DataFrame,
    laps: pd.DataFrame,
    transitions: pd.DataFrame,
    events: list[_Event],
    event: _Event,
    event_key: str,
    race_name: str,
    references: pd.DataFrame | None = None,
) -> tuple[list[dict[str, object]], dict[str, dict[str, object]]]:
    if references is None:
        references = _green_reference_losses(replay, laps, transitions, events)
    replay_by_driver = _replay_driver_frames(replay)
    state_cache: dict[tuple[str, float], dict[str, object] | None] = {}
    rows: list[dict[str, object]] = []
    diagnostics: dict[str, dict[str, object]] = {}
    during = transitions.loc[
        transitions["pit_in_t_s"].ge(event.start_t_s)
        & transitions["pit_in_t_s"].le(
            event.end_t_s if event.end_t_s is not None else event.start_t_s
        )
    ]
    for _, transition in during.iterrows():
        driver = str(transition["driver_code"])
        actual_loss, peer_count = _pairwise_pit_loss(
            replay,
            transition,
            transitions,
            replay_by_driver=replay_by_driver,
            state_cache=state_cache,
        )
        base = {
            "season": int(transition["season"]),
            "round": int(transition["round"]),
            "race_name": race_name,
            "event_id": event_key,
            "event_number": event.event_number,
            "event_type": event.event_type,
            "driver_code": driver,
            "effect_scope": "pit_stop",
            "unit": "seconds",
            "methodology_version": METHODOLOGY_VERSION,
        }
        actual_eligible = np.isfinite(actual_loss) and peer_count >= 1
        actual_reason = (
            "" if actual_eligible else "No comparable non-pitting peer or incomplete replay timing"
        )
        rows.append(
            {
                **base,
                "effect_type": "observed_pit_relative_loss",
                "value": actual_loss,
                "lower_bound": np.nan,
                "upper_bound": np.nan,
                "evidence_class": "observed" if actual_eligible else "unavailable",
                "confidence": (
                    "high"
                    if actual_eligible and peer_count >= MIN_TIME_COMPARABLE_DRIVERS
                    else "medium"
                    if actual_eligible
                    else "insufficient"
                ),
                "sample_size": peer_count,
                "eligible": actual_eligible,
                "exclusion_reason": actual_reason,
            }
        )
        reference_count = len(references)
        reference_drivers = references["driver_code"].nunique() if not references.empty else 0
        reason = actual_reason
        if not reason and reference_count < MIN_PIT_REFERENCE_STOPS:
            reason = "Fewer than 5 clean green-flag reference stops"
        elif not reason and reference_drivers < MIN_PIT_REFERENCE_DRIVERS:
            reason = "Green-flag references cover fewer than 4 drivers"
        normalized = np.array([], dtype=float)
        mad = np.nan
        if not reason:
            normalized = (
                references["observed_loss_sec"]
                - (references["duration_sec"] - float(transition["duration_sec"]))
            ).to_numpy(dtype=float)
            centre = float(np.median(normalized))
            mad = float(np.median(np.abs(normalized - centre)))
            if not np.isfinite(mad) or mad > MAX_PIT_REFERENCE_MAD_S:
                reason = "Green-flag pit-loss reference is unstable"
        estimate = lower = upper = green_loss = np.nan
        confidence = "insufficient"
        if not reason:
            green_loss = float(np.median(normalized))
            estimate = green_loss - actual_loss
            seed_key = f"{event_key}:{driver}:pit-opportunity"
            seed = int.from_bytes(hashlib.sha256(seed_key.encode()).digest()[:8], "little")
            generator = np.random.default_rng(seed)
            samples = (
                np.median(
                    generator.choice(
                        normalized,
                        size=(PIT_BOOTSTRAP_SAMPLES, len(normalized)),
                        replace=True,
                    ),
                    axis=1,
                )
                - actual_loss
            )
            lower = float(np.quantile(samples, 0.05) - TIMING_RESOLUTION_S)
            upper = float(np.quantile(samples, 0.95) + TIMING_RESOLUTION_S)
            confidence = (
                "high"
                if reference_count >= HIGH_PIT_REFERENCE_STOPS
                and reference_drivers >= HIGH_PIT_REFERENCE_DRIVERS
                and mad <= HIGH_PIT_REFERENCE_MAD_S
                and peer_count >= MIN_TIME_COMPARABLE_DRIVERS
                else "medium"
            )
        eligible = not reason
        saving_effect_type = (
            "estimated_vsc_pit_saving"
            if event.event_type == "VSC"
            else "estimated_safety_car_pit_saving"
        )
        for effect_type, value, bounds in (
            ("estimated_green_pit_loss", green_loss, (np.nan, np.nan)),
            (saving_effect_type, estimate, (lower, upper)),
        ):
            rows.append(
                {
                    **base,
                    "effect_type": effect_type,
                    "value": value,
                    "lower_bound": bounds[0],
                    "upper_bound": bounds[1],
                    "evidence_class": "estimated" if eligible else "unavailable",
                    "confidence": confidence,
                    "sample_size": reference_count,
                    "eligible": eligible,
                    "exclusion_reason": reason,
                }
            )
        diagnostics[driver] = {
            "eligible": eligible,
            "reason": reason,
            "actual_loss": actual_loss,
            "saving": estimate,
            "confidence": confidence,
        }
    return rows, diagnostics


def _to_int(value: object) -> int | None:
    if pd.isna(value):
        return None
    return int(float(str(value)))


def _to_float(value: object) -> float:
    converted = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return float(converted) if pd.notna(converted) else np.nan


def _outcome(eligible: bool, positions_gained: int | None, active_after: bool) -> str:
    if not active_after:
        return "No post-event timing"
    if not eligible or positions_gained is None:
        return "Excluded"
    if positions_gained > 0:
        return "Observed position gain"
    if positions_gained < 0:
        return "Observed position loss"
    return "Position held"


_STORY_POSITION_THRESHOLD = 1.0
_STORY_TIME_THRESHOLD_S = 0.5
_STORY_DIRECT_EFFECTS = {
    "observed_position_change": _STORY_POSITION_THRESHOLD,
    "field_adjusted_gap_change": _STORY_TIME_THRESHOLD_S,
    "restart_position_change": _STORY_POSITION_THRESHOLD,
    "restart_gap_change": _STORY_TIME_THRESHOLD_S,
}
_STORY_PIT_EFFECTS = {
    "estimated_vsc_pit_saving",
    "estimated_safety_car_pit_saving",
}


def _story_classification(
    driver: dict[str, object], effects: list[dict[str, object]]
) -> dict[str, object]:
    """Summarise evaluated, non-duplicated effects into one driver story state."""
    evaluated = 0
    material = 0
    directions: set[str] = set()

    for effect in effects:
        if str(effect.get("driver_code")) != str(driver.get("driver_code")):
            continue
        effect_type = str(effect.get("effect_type"))
        eligible = bool(effect.get("eligible"))
        value = _to_float(effect.get("value"))
        if effect_type in _STORY_DIRECT_EFFECTS and eligible and np.isfinite(value):
            evaluated += 1
            if abs(value) >= _STORY_DIRECT_EFFECTS[effect_type]:
                material += 1
                directions.add("benefit" if value > 0 else "loss")
        elif effect_type in _STORY_PIT_EFFECTS and eligible and np.isfinite(value):
            evaluated += 1
            lower = _to_float(effect.get("lower_bound"))
            upper = _to_float(effect.get("upper_bound"))
            # A pit counterfactual is material only when its complete 90% interval
            # lies on one side of zero. The point estimate alone is not enough.
            if np.isfinite(lower) and np.isfinite(upper) and (lower > 0 or upper < 0):
                material += 1
                directions.add("benefit" if lower > 0 else "loss")

    tyre_change = bool(driver.get("tyre_eligible")) and bool(
        driver.get("tyre_changed_during_suspension")
    )
    if tyre_change:
        evaluated += 1
        material += 1

    if material:
        direction = (
            "mixed"
            if directions == {"benefit", "loss"}
            else next(iter(directions))
            if directions
            else "unknown"
        )
        return {
            "story_status": "material_impact",
            "story_direction": direction,
            "story_reason": f"{material} material effect(s) exceed the publication threshold",
            "material_effect_count": material,
            "evaluated_effect_count": evaluated,
        }

    pit_timing = str(driver.get("pit_timing_class") or "")
    pit_effect = next(
        (
            effect
            for effect in effects
            if str(effect.get("driver_code")) == str(driver.get("driver_code"))
            and str(effect.get("effect_type")) in _STORY_PIT_EFFECTS
        ),
        None,
    )
    if pit_timing == "after_end":
        reason = "Pit stop occurred after the neutralisation ended"
    elif pit_timing == "during_neutralisation" and pit_effect is not None:
        reason = (
            "Pit stop observed, but its estimated saving/loss interval crosses zero"
            if bool(pit_effect.get("eligible"))
            else "Pit stop observed; trustworthy counterfactual unavailable"
        )
    elif pit_timing == "during_neutralisation":
        reason = "Pit stop observed; trustworthy counterfactual unavailable"
    elif pit_timing == "unresolved":
        reason = "Strategic action inferred, but exact timing is unavailable"
    elif evaluated:
        return {
            "story_status": "no_material_effect",
            "story_direction": "neutral",
            "story_reason": f"{evaluated} evaluated effect(s) remain below materiality thresholds",
            "material_effect_count": 0,
            "evaluated_effect_count": evaluated,
        }
    else:
        reason = "Trustworthy component evidence is unavailable"
    return {
        "story_status": "context_only",
        "story_direction": "unknown",
        "story_reason": reason,
        "material_effect_count": 0,
        "evaluated_effect_count": evaluated,
    }


def _driver_rows(
    replay: pd.DataFrame,
    event: _Event,
    event_key: str,
    pre: pd.DataFrame,
    post: pd.DataFrame,
    event_eligible: bool,
    event_reason: str,
    event_confidence: str,
    post_t_s: float | None,
    transitions: pd.DataFrame,
) -> list[dict[str, object]]:
    post_by_driver = post.set_index("driver_code", drop=False)
    intervention_end = event.end_t_s if event.end_t_s is not None else event.start_t_s
    intervention = replay.loc[replay["t_s"].between(event.start_t_s, intervention_end)]
    recovery = replay.loc[
        replay["t_s"].between(intervention_end, post_t_s, inclusive="right")
        if post_t_s is not None
        else replay["t_s"].eq(np.inf)
    ]
    deficits_pre = _estimated_lap_deficits(pre)
    deficits_post = _estimated_lap_deficits(post)

    rows: list[dict[str, object]] = []
    for before in pre.itertuples(index=False):
        driver = str(before.driver_code)
        after: pd.Series | None = None
        if driver in post_by_driver.index:
            selected = post_by_driver.loc[driver]
            after = selected.iloc[0] if isinstance(selected, pd.DataFrame) else selected
        active_after = after is not None
        position_before = _to_int(before.running_order)
        position_after = _to_int(after["running_order"]) if after is not None else None
        position_before_source = _source_value(before.running_order_source)
        position_after_source = (
            _source_value(after["running_order_source"]) if after is not None else ""
        )
        position_evidence_class = _evidence_class(position_before_source, position_after_source)
        positions_gained = (
            position_before - position_after
            if position_before is not None and position_after is not None
            else None
        )
        lap_before = _to_int(before.lap_number)
        lap_after = _to_int(after["lap_number"]) if after is not None else None
        deficit_before = deficits_pre.get(driver)
        deficit_after = deficits_post.get(driver)
        deficit_changed = (
            deficit_before != deficit_after
            if deficit_before is not None and deficit_after is not None
            else None
        )
        gap_before = float(before.gap_to_leader_s) if pd.notna(before.gap_to_leader_s) else np.nan
        gap_after = (
            float(after["gap_to_leader_s"])
            if after is not None and pd.notna(after["gap_to_leader_s"])
            else np.nan
        )
        gap_before_source = _source_value(before.gap_source)
        gap_after_source = _source_value(after["gap_source"]) if after is not None else ""
        gap_evidence_class = _evidence_class(gap_before_source, gap_after_source)
        raw_gap_gain = (
            gap_before - gap_after
            if event.event_type != "Red Flag"
            and gap_evidence_class != "unavailable"
            and deficit_changed is not None
            and not deficit_changed
            and np.isfinite(gap_before)
            and np.isfinite(gap_after)
            else np.nan
        )
        stint_before = _to_int(before.stint)
        stint_after = _to_int(after["stint"]) if after is not None else None
        intervention_driver = intervention.loc[intervention["driver_code"].eq(driver)]
        recovery_driver = recovery.loc[recovery["driver_code"].eq(driver)]
        intervention_max = pd.to_numeric(intervention_driver["stint"], errors="coerce").max()
        recovery_max = pd.to_numeric(recovery_driver["stint"], errors="coerce").max()
        pitted_intervention = bool(
            event.event_type != "Red Flag"
            and stint_before is not None
            and pd.notna(intervention_max)
            and intervention_max > stint_before
        )
        recovery_baseline = intervention_max if pd.notna(intervention_max) else stint_before
        pitted_recovery = bool(
            event.event_type != "Red Flag"
            and recovery_baseline is not None
            and pd.notna(recovery_max)
            and recovery_max > recovery_baseline
        )
        driver_transitions = transitions.loc[transitions["driver_code"].eq(driver)]
        relevant_transition: pd.Series | None = None
        pit_timing_class = "no_stop_observed"
        if not driver_transitions.empty:
            classified = driver_transitions.assign(
                _class=driver_transitions.apply(
                    lambda row: _pit_classification(row, event, post_t_s), axis=1
                )
            )
            relevant = classified.loc[
                classified["_class"].isin(["during_neutralisation", "after_end"])
            ].sort_values("pit_in_t_s")
            if not relevant.empty:
                relevant_transition = relevant.iloc[0]
                pit_timing_class = str(relevant_transition["_class"])
        if relevant_transition is None and (pitted_intervention or pitted_recovery):
            pit_timing_class = "unresolved"
        stop_count = (
            max(0, stint_after - stint_before)
            if stint_before is not None and stint_after is not None
            else 0
        )
        compound_before = str(before.compound) if pd.notna(before.compound) else ""
        compound_after = (
            str(after["compound"]) if after is not None and pd.notna(after["compound"]) else ""
        )
        tyre_changed_red = bool(
            event.event_type == "Red Flag"
            and compound_before
            and compound_after
            and (compound_before != compound_after or stop_count > 0)
        )
        before_offset = float(before.capture_offset_s)
        after_offset = float(after["capture_offset_s"]) if after is not None else np.nan
        driver_eligible = bool(
            event_eligible
            and active_after
            and position_before is not None
            and position_after is not None
            and position_evidence_class != "unavailable"
            and before_offset <= MAX_CAPTURE_OFFSET_S
            and after_offset <= MAX_CAPTURE_OFFSET_S
        )
        position_eligible = bool(
            event.status == "complete"
            and active_after
            and position_before is not None
            and position_after is not None
            and position_evidence_class != "unavailable"
            and before_offset <= MAX_CAPTURE_OFFSET_S
            and after_offset <= MAX_CAPTURE_OFFSET_S
        )
        pit_eligible = relevant_transition is not None
        tyre_eligible = bool(
            position_eligible and compound_before and compound_after and stint_before is not None
        )
        reason = event_reason
        if not active_after:
            reason = "No post-event timing"
        elif position_before is None or position_after is None:
            reason = "Incomplete position timing"
        elif position_evidence_class == "unavailable":
            reason = "Position provenance unavailable"
        confidence = event_confidence if driver_eligible else "Low"
        time_reason = ""
        if not driver_eligible:
            time_reason = reason
        elif event.event_type == "Red Flag":
            time_reason = "Red flag: position evidence only"
        elif deficit_changed is None:
            time_reason = "Lap deficit unavailable or near an uncertain boundary"
        elif deficit_changed:
            time_reason = "Estimated lap deficit changed"
        elif gap_evidence_class == "unavailable":
            time_reason = "Gap provenance unavailable"
        elif not np.isfinite(raw_gap_gain):
            time_reason = "Incomplete gap timing"
        rows.append(
            {
                "season": int(before.season),
                "round": int(before.round),
                "race_name": str(before.race_name),
                "event_id": event_key,
                "event_number": event.event_number,
                "event_type": event.event_type,
                "driver_code": driver,
                "driver_name": str(before.driver_name),
                "team": str(before.team),
                "position_before": position_before,
                "position_after": position_after,
                "positions_gained": positions_gained,
                "position_before_source": position_before_source,
                "position_after_source": position_after_source,
                "position_before_confidence": _source_value(before.running_order_confidence),
                "position_after_confidence": (
                    _source_value(after["running_order_confidence"]) if after is not None else ""
                ),
                "position_before_observed_t_s": _to_float(before.running_order_observed_t_s),
                "position_after_observed_t_s": (
                    _to_float(after["running_order_observed_t_s"]) if after is not None else np.nan
                ),
                "position_evidence_class": position_evidence_class,
                "gap_to_leader_before_s": gap_before,
                "gap_to_leader_after_s": gap_after,
                "raw_gap_gain_s": raw_gap_gain,
                "field_adjusted_gap_gain_s": np.nan,
                "gap_before_source": gap_before_source,
                "gap_after_source": gap_after_source,
                "gap_before_confidence": _source_value(before.gap_confidence),
                "gap_after_confidence": (
                    _source_value(after["gap_confidence"]) if after is not None else ""
                ),
                "gap_before_observed_t_s": _to_float(before.gap_observed_t_s),
                "gap_after_observed_t_s": (
                    _to_float(after["gap_observed_t_s"]) if after is not None else np.nan
                ),
                "gap_evidence_class": gap_evidence_class,
                "time_comparable_driver_count": 0,
                "time_eligible": not time_reason,
                "time_exclusion_reason": time_reason,
                "lap_before": lap_before,
                "lap_after": lap_after,
                "lap_deficit_before": deficit_before,
                "lap_deficit_after": deficit_after,
                "lap_deficit_changed": deficit_changed,
                "stint_before": stint_before,
                "stint_after": stint_after,
                "compound_before": compound_before,
                "compound_after": compound_after,
                "tyre_life_before": _to_int(before.tyre_life),
                "tyre_life_after": _to_int(after["tyre_life"]) if after is not None else None,
                "pitted_during_intervention": pitted_intervention,
                "pitted_during_recovery": pitted_recovery,
                "pit_timing_class": pit_timing_class,
                "pit_in_t_s": (
                    float(relevant_transition["pit_in_t_s"])
                    if relevant_transition is not None
                    else np.nan
                ),
                "pit_out_t_s": (
                    float(relevant_transition["pit_out_t_s"])
                    if relevant_transition is not None
                    else np.nan
                ),
                "pit_duration_sec": (
                    float(relevant_transition["duration_sec"])
                    if relevant_transition is not None
                    else np.nan
                ),
                "stop_count": stop_count,
                "tyre_changed_during_suspension": tyre_changed_red,
                "active_after": active_after,
                "position_eligible": position_eligible,
                "gap_eligible": False,
                "pit_eligible": pit_eligible,
                "restart_eligible": bool(driver_eligible),
                "tyre_eligible": tyre_eligible,
                "story_status": "context_only",
                "story_direction": "unknown",
                "story_reason": "Trustworthy component evidence is unavailable",
                "material_effect_count": 0,
                "evaluated_effect_count": 0,
                "focus_rank": None,
                "eligible": driver_eligible,
                "exclusion_reason": "" if driver_eligible else reason,
                "confidence": confidence,
                "outcome_label": _outcome(position_eligible, positions_gained, active_after),
                "timing_before_offset_s": before_offset,
                "timing_after_offset_s": after_offset,
                "methodology_version": METHODOLOGY_VERSION,
            }
        )
    return rows


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


def analyse_race_control_impact(
    replay: pd.DataFrame,
    race_control: pd.DataFrame,
    laps: pd.DataFrame,
    stops: pd.DataFrame | None = None,
    *,
    min_event_drivers: int = DEFAULT_MIN_EVENT_DRIVERS,
) -> RaceControlImpactResult:
    """Build event summaries and driver evidence for every exact neutralisation pair."""
    _require_columns(replay, _REPLAY_REQUIRED, "replay")
    _require_columns(race_control, _CONTROL_REQUIRED, "race_control")
    _require_columns(laps, _LAPS_REQUIRED, "laps")
    prepared_stops = _prepare_stops(stops)
    if min_event_drivers < 1:
        raise ValueError("min_event_drivers must be at least one")
    if race_control.empty:
        return _empty_result()

    replay = replay.copy()
    race_control = race_control.copy()
    laps = laps.copy()
    for column, default in _REPLAY_PROVENANCE_DEFAULTS.items():
        if column not in replay:
            replay[column] = default
    for column in ("pit_in_t_s", "pit_out_t_s", "compound"):
        if column not in laps:
            laps[column] = np.nan if column != "compound" else ""
    for frame in (replay, race_control, laps):
        for column in ("season", "round"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in ("t_s", "lap_number", "lap_progress", "stint", "tyre_life", "running_order"):
        replay[column] = pd.to_numeric(replay[column], errors="coerce")
    replay["gap_to_leader_s"] = pd.to_numeric(replay["gap_to_leader_s"], errors="coerce")
    race_control["t_s"] = pd.to_numeric(race_control["t_s"], errors="coerce")
    race_control["lap"] = pd.to_numeric(race_control["lap"], errors="coerce")
    laps["lap_number"] = pd.to_numeric(laps["lap_number"], errors="coerce")
    for column in ("lap_start_t_s", "lap_end_t_s"):
        laps[column] = pd.to_numeric(laps[column], errors="coerce").replace(
            [np.inf, -np.inf], np.nan
        )
    for column in ("pit_in_t_s", "pit_out_t_s"):
        laps[column] = pd.to_numeric(laps[column], errors="coerce").replace(
            [np.inf, -np.inf], np.nan
        )

    event_rows: list[dict[str, object]] = []
    evidence_rows: list[dict[str, object]] = []
    checkpoint_rows: list[dict[str, object]] = []
    effect_rows: list[dict[str, object]] = []
    grouped = race_control.dropna(subset=[*_RACE_KEYS, "t_s"]).groupby(_RACE_KEYS, sort=True)
    for keys, control_race in grouped:
        season, rnd = (int(keys[0]), int(keys[1]))
        replay_race = replay.loc[replay["season"].eq(season) & replay["round"].eq(rnd)]
        laps_race = laps.loc[laps["season"].eq(season) & laps["round"].eq(rnd)]
        stops_race = prepared_stops.loc[
            prepared_stops["season"].eq(season) & prepared_stops["round"].eq(rnd)
        ]
        transitions = _pit_transitions(laps_race, stops_race)
        events = _extract_events(control_race)
        green_references = (
            _green_reference_losses(replay_race, laps_race, transitions, events)
            if not replay_race.empty and not transitions.empty
            else pd.DataFrame()
        )
        for event in events:
            event_key = _event_id(season, rnd, event)
            race_name = (
                str(replay_race["race_name"].dropna().iloc[0])
                if not replay_race["race_name"].dropna().empty
                else str(control_race["race_name"].dropna().iloc[0])
                if not control_race["race_name"].dropna().empty
                else "Unknown race"
            )
            checkpoint = _post_checkpoint(replay_race, event) if not replay_race.empty else None
            post_t_s, post_lap = checkpoint if checkpoint is not None else (None, None)
            pre = (
                _snapshot(replay_race, event.start_t_s, before=True)
                if not replay_race.empty
                else replay_race
            )
            post = (
                _snapshot(replay_race, post_t_s, before=False)
                if post_t_s is not None
                else replay_race.iloc[0:0]
            )
            later_start = next(
                (
                    other.start_t_s
                    for other in events
                    if event.end_t_s is not None
                    and post_t_s is not None
                    and event.end_t_s < other.start_t_s <= post_t_s
                ),
                None,
            )
            recovery_interrupted = later_start is not None
            recovery_clean = _recovery_clean(laps_race, replay_race, event, checkpoint)
            reason = event.parse_reason or ""
            if not reason and replay_race.empty:
                reason = "Replay unavailable"
            elif not reason and pre.empty:
                reason = "No pre-event baseline"
            elif not reason and checkpoint is None:
                reason = "Two-lap recovery unavailable"
            elif not reason and recovery_interrupted:
                reason = "Recovery interrupted by another neutralisation"
            elif not reason and len(pre) < min_event_drivers:
                reason = f"Fewer than {min_event_drivers} pre-event drivers"
            elif not reason and not recovery_clean:
                reason = "Two complete green recovery laps not verified"
            event_eligible = not reason
            offsets = pd.concat(
                [
                    pre.get("capture_offset_s", pd.Series(dtype="float64")),
                    post.get("capture_offset_s", pd.Series(dtype="float64")),
                ]
            )
            confidence = "Low"
            if event_eligible:
                high = (
                    event.event_type in {"Safety Car", "VSC"}
                    and len(pre) >= 15
                    and recovery_clean
                    and not offsets.empty
                    and offsets.max() <= HIGH_CONFIDENCE_OFFSET_S
                )
                confidence = "High" if high else "Medium"
            driver_rows = _driver_rows(
                replay_race,
                event,
                event_key,
                pre,
                post,
                event_eligible,
                reason,
                confidence,
                post_t_s,
                transitions,
            )
            comparable = [row for row in driver_rows if bool(row["time_eligible"])]
            time_count = len(comparable)
            time_reason = reason or (
                "Red flag: position evidence only"
                if event.event_type == "Red Flag"
                else f"Fewer than {MIN_TIME_COMPARABLE_DRIVERS} comparable time drivers"
                if time_count < MIN_TIME_COMPARABLE_DRIVERS
                else ""
            )
            median = (
                float(np.median([row["raw_gap_gain_s"] for row in comparable]))
                if not time_reason
                else np.nan
            )
            for row in driver_rows:
                row["time_comparable_driver_count"] = time_count
                if row["time_eligible"]:
                    row["time_eligible"] = not time_reason
                    row["time_exclusion_reason"] = time_reason
                    if not time_reason:
                        row["field_adjusted_gap_gain_s"] = (
                            float(str(row["raw_gap_gain_s"])) - median
                        )
                        row["gap_eligible"] = True

            event_effects: list[dict[str, object]] = []
            for row in driver_rows:
                base_effect = {
                    "season": season,
                    "round": rnd,
                    "race_name": race_name,
                    "event_id": event_key,
                    "event_number": event.event_number,
                    "event_type": event.event_type,
                    "driver_code": row["driver_code"],
                    "methodology_version": METHODOLOGY_VERSION,
                }
                for effect_type, value, unit, is_eligible, effect_reason, evidence_class in (
                    (
                        "observed_position_change",
                        row["positions_gained"],
                        "positions",
                        row["position_eligible"],
                        "" if row["position_eligible"] else row["exclusion_reason"],
                        row["position_evidence_class"],
                    ),
                    (
                        "observed_gap_change",
                        row["raw_gap_gain_s"],
                        "seconds",
                        row["gap_eligible"],
                        "" if row["gap_eligible"] else row["time_exclusion_reason"],
                        row["gap_evidence_class"],
                    ),
                    (
                        "field_adjusted_gap_change",
                        row["field_adjusted_gap_gain_s"],
                        "seconds",
                        row["gap_eligible"],
                        "" if row["gap_eligible"] else row["time_exclusion_reason"],
                        row["gap_evidence_class"],
                    ),
                    (
                        "observed_tyre_change",
                        1.0 if row["stint_after"] != row["stint_before"] else 0.0,
                        "boolean",
                        row["tyre_eligible"],
                        "" if row["tyre_eligible"] else "Tyre state unavailable",
                        "recorded",
                    ),
                ):
                    event_effects.append(
                        {
                            **base_effect,
                            "effect_type": effect_type,
                            "effect_scope": "event_window",
                            "value": value if is_eligible else np.nan,
                            "lower_bound": np.nan,
                            "upper_bound": np.nan,
                            "unit": unit,
                            "evidence_class": evidence_class if is_eligible else "unavailable",
                            "confidence": confidence.lower() if is_eligible else "insufficient",
                            "sample_size": 1 if is_eligible else 0,
                            "eligible": is_eligible,
                            "exclusion_reason": effect_reason,
                        }
                    )
            pit_diagnostics: dict[str, dict[str, object]] = {}
            if event.event_type in {"VSC", "Safety Car"} and not transitions.empty:
                pit_effects, pit_diagnostics = _pit_effect_rows(
                    replay_race,
                    laps_race,
                    transitions,
                    events,
                    event,
                    event_key,
                    race_name,
                    green_references,
                )
                event_effects.extend(pit_effects)

            event_checkpoints: list[dict[str, object]] = []
            if not replay_race.empty:
                green_one_t_s = _green_one_checkpoint(replay_race, event)
                common = [
                    ("pre_deploy", 10, event.start_t_s),
                    ("control_end", 40, event.end_t_s),
                    ("green_lap_1", 70, green_one_t_s),
                    ("green_lap_3", 90, post_t_s),
                ]
                for checkpoint_type, checkpoint_order, checkpoint_t_s in common:
                    if checkpoint_t_s is None:
                        continue
                    for driver in replay_race["driver_code"].dropna().astype(str).unique():
                        event_checkpoints.append(
                            _checkpoint_row(
                                replay_race,
                                event,
                                event_key,
                                race_name,
                                driver,
                                checkpoint_type,
                                checkpoint_order,
                                float(checkpoint_t_s),
                                source="official_race_control+race_replay",
                            )
                        )
                relevant_transitions = transitions.loc[
                    transitions["pit_in_t_s"].ge(event.start_t_s)
                    & transitions["pit_in_t_s"].le(post_t_s if post_t_s is not None else np.inf)
                ]
                for _, transition in relevant_transitions.iterrows():
                    for checkpoint_type, checkpoint_order, column in (
                        ("pit_in", 20, "pit_in_t_s"),
                        ("pit_out", 30, "pit_out_t_s"),
                    ):
                        event_checkpoints.append(
                            _checkpoint_row(
                                replay_race,
                                event,
                                event_key,
                                race_name,
                                str(transition["driver_code"]),
                                checkpoint_type,
                                checkpoint_order,
                                float(transition[column]),
                                source="fastf1_pit_timing+race_replay",
                            )
                        )
                _invalidate_incoherent_checkpoint_orders(event_checkpoints)

            checkpoint_by_key = {
                (row["driver_code"], row["checkpoint_type"]): row
                for row in event_checkpoints
                if bool(row["eligible"])
            }
            for row in driver_rows:
                driver = str(row["driver_code"])
                end_state = checkpoint_by_key.get((driver, "control_end"))
                green_state = checkpoint_by_key.get((driver, "green_lap_3"))
                restart_ok = end_state is not None and green_state is not None and recovery_clean
                restart_position_class = (
                    _evidence_class(
                        end_state.get("running_order_source"),
                        green_state.get("running_order_source"),
                    )
                    if end_state is not None and green_state is not None
                    else "unavailable"
                )
                restart_gap_class = (
                    _evidence_class(end_state.get("gap_source"), green_state.get("gap_source"))
                    if end_state is not None and green_state is not None
                    else "unavailable"
                )
                row["restart_eligible"] = restart_ok
                restart_reason = (
                    "" if restart_ok else "Verified green recovery checkpoints unavailable"
                )
                position_change = np.nan
                gap_change = np.nan
                if end_state is not None and green_state is not None and restart_ok:
                    end_position = _to_int(end_state.get("running_order"))
                    green_position = _to_int(green_state.get("running_order"))
                    if end_position is not None and green_position is not None:
                        position_change = end_position - green_position
                    end_gap = pd.to_numeric(
                        pd.Series([end_state.get("gap_to_leader_s")]), errors="coerce"
                    ).iloc[0]
                    green_gap = pd.to_numeric(
                        pd.Series([green_state.get("gap_to_leader_s")]), errors="coerce"
                    ).iloc[0]
                    if event.event_type != "Red Flag" and pd.notna(end_gap) and pd.notna(green_gap):
                        gap_change = float(end_gap - green_gap)
                for effect_type, value, unit, metric_ok, evidence_class in (
                    (
                        "restart_position_change",
                        position_change,
                        "positions",
                        restart_ok
                        and restart_position_class != "unavailable"
                        and np.isfinite(position_change),
                        restart_position_class,
                    ),
                    (
                        "restart_gap_change",
                        gap_change,
                        "seconds",
                        restart_ok
                        and restart_gap_class != "unavailable"
                        and event.event_type != "Red Flag"
                        and np.isfinite(gap_change),
                        restart_gap_class,
                    ),
                ):
                    event_effects.append(
                        {
                            "season": season,
                            "round": rnd,
                            "race_name": race_name,
                            "event_id": event_key,
                            "event_number": event.event_number,
                            "event_type": event.event_type,
                            "driver_code": driver,
                            "effect_type": effect_type,
                            "effect_scope": "control_end_to_green_lap_3",
                            "value": value if metric_ok else np.nan,
                            "lower_bound": np.nan,
                            "upper_bound": np.nan,
                            "unit": unit,
                            "evidence_class": evidence_class if metric_ok else "unavailable",
                            "confidence": confidence.lower() if metric_ok else "insufficient",
                            "sample_size": 1 if metric_ok else 0,
                            "eligible": metric_ok,
                            "exclusion_reason": "" if metric_ok else restart_reason,
                            "methodology_version": METHODOLOGY_VERSION,
                        }
                    )

            for row in driver_rows:
                row.update(_story_classification(row, event_effects))
            story_priority = {
                "material_impact": 0,
                "context_only": 1,
                "no_material_effect": 2,
            }
            material_pit_drivers = {
                str(effect["driver_code"])
                for effect in event_effects
                if str(effect["effect_type"]) in _STORY_PIT_EFFECTS
                and bool(effect["eligible"])
                and (_to_float(effect["lower_bound"]) > 0 or _to_float(effect["upper_bound"]) < 0)
            }
            ranked = sorted(
                driver_rows,
                key=lambda row: (
                    story_priority[str(row["story_status"])],
                    0 if str(row["driver_code"]) in material_pit_drivers else 1,
                    0 if row["pit_timing_class"] == "during_neutralisation" else 1,
                    _to_int(row["position_before"])
                    if _to_int(row["position_before"]) is not None
                    else 999,
                    -(_to_int(row["material_effect_count"]) or 0),
                    -(_to_int(row["positions_gained"]) or 0),
                    str(row["driver_code"]),
                ),
            )
            for rank, row in enumerate(ranked, start=1):
                row["focus_rank"] = rank
            focus_driver = str(ranked[0]["driver_code"]) if ranked else ""
            evidence_rows.extend(driver_rows)
            checkpoint_rows.extend(event_checkpoints)
            effect_rows.extend(event_effects)
            eligible_driver_rows = [row for row in driver_rows if bool(row["eligible"])]
            position_rows = [row for row in driver_rows if bool(row["position_eligible"])]
            tyre_rows = [row for row in driver_rows if bool(row["tyre_eligible"])]
            pit_rows = [row for row in driver_rows if bool(row["pit_eligible"])]
            event_rows.append(
                {
                    "season": season,
                    "round": rnd,
                    "race_name": race_name,
                    "event_id": event_key,
                    "event_number": event.event_number,
                    "event_type": event.event_type,
                    "start_t_s": event.start_t_s,
                    "end_t_s": event.end_t_s,
                    "post_checkpoint_t_s": post_t_s,
                    "deployment_lap": event.start_lap,
                    "end_lap": event.end_lap,
                    "post_checkpoint_lap": post_lap,
                    "duration_s": (
                        event.end_t_s - event.start_t_s if event.end_t_s is not None else np.nan
                    ),
                    "event_status": event.status,
                    "recovery_clean": recovery_clean,
                    "pre_driver_count": len(pre),
                    "post_driver_count": len(post),
                    "eligible_driver_count": len(eligible_driver_rows),
                    "time_comparable_driver_count": time_count,
                    "time_eligible": not time_reason,
                    "time_exclusion_reason": time_reason,
                    "intervention_stop_count": sum(
                        bool(row["pitted_during_intervention"]) for row in driver_rows
                    ),
                    "recovery_stop_count": sum(
                        bool(row["pitted_during_recovery"]) for row in driver_rows
                    ),
                    "position_gainer_count": sum(
                        float(str(row["positions_gained"] or 0)) > 0 for row in position_rows
                    ),
                    "position_loser_count": sum(
                        float(str(row["positions_gained"] or 0)) < 0 for row in position_rows
                    ),
                    "position_status": (
                        "recorded"
                        if position_rows
                        and all(
                            row["position_evidence_class"] == "recorded" for row in position_rows
                        )
                        else "estimated"
                        if position_rows
                        else "unavailable"
                    ),
                    "gap_status": (
                        "recorded"
                        if not time_reason
                        and comparable
                        and all(row["gap_evidence_class"] == "recorded" for row in comparable)
                        else "estimated"
                        if not time_reason and comparable
                        else "unavailable"
                    ),
                    "pit_status": (
                        "estimated"
                        if any(bool(item.get("eligible")) for item in pit_diagnostics.values())
                        else "observed"
                        if pit_rows
                        else "unavailable"
                    ),
                    "restart_status": "observed" if recovery_clean else "unavailable",
                    "tyre_status": "observed" if tyre_rows else "unavailable",
                    "focus_driver_code": focus_driver,
                    "eligible": event_eligible,
                    "exclusion_reason": reason,
                    "confidence": confidence,
                    "methodology_version": METHODOLOGY_VERSION,
                }
            )

    events_frame = _cast_frame(
        pd.DataFrame(event_rows),
        RACE_CONTROL_EVENT_COLUMNS,
        _EVENT_INTEGER,
        _EVENT_FLOAT,
        _EVENT_BOOLEAN,
    )
    evidence_frame = _cast_frame(
        pd.DataFrame(evidence_rows),
        RACE_CONTROL_IMPACT_COLUMNS,
        _IMPACT_INTEGER,
        _IMPACT_FLOAT,
        _IMPACT_BOOLEAN,
    )
    checkpoint_frame = _cast_frame(
        pd.DataFrame(checkpoint_rows),
        RACE_CONTROL_CHECKPOINT_COLUMNS,
        _CHECKPOINT_INTEGER,
        _CHECKPOINT_FLOAT,
        _CHECKPOINT_BOOLEAN,
    )
    effect_frame = _cast_frame(
        pd.DataFrame(effect_rows),
        RACE_CONTROL_EFFECT_COLUMNS,
        _EFFECT_INTEGER,
        _EFFECT_FLOAT,
        _EFFECT_BOOLEAN,
    )
    if not evidence_frame.empty:
        evidence_frame = evidence_frame.sort_values(
            ["season", "round", "event_number", "position_before"]
        ).reset_index(drop=True)
    return RaceControlImpactResult(
        events=events_frame.sort_values(["season", "round", "event_number"]).reset_index(drop=True),
        evidence=evidence_frame,
        checkpoints=checkpoint_frame.sort_values(
            ["season", "round", "event_number", "driver_code", "checkpoint_order"]
        ).reset_index(drop=True),
        effects=effect_frame.sort_values(
            ["season", "round", "event_number", "driver_code", "effect_type"]
        ).reset_index(drop=True),
    )
