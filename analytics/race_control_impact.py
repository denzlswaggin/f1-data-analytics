"""Observed position and gap changes across race-control neutralisations.

Safety-car, virtual-safety-car and red-flag periods are reconstructed from the
official race-control messages.  Each driver's state immediately before the
deployment is compared with the first reliable replay state after the period.
The result is descriptive evidence: field compression, pit timing, retirements
and the restart can all contribute to the observed change.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

METHODOLOGY_VERSION = "race-control-impact-v1"
MAX_CAPTURE_OFFSET_S = 5.0
HIGH_CONFIDENCE_OFFSET_S = 2.0

_RACE_KEYS = ["season", "round"]
_REPLAY_REQUIRED = {
    *_RACE_KEYS,
    "race_name",
    "driver_code",
    "driver_name",
    "team",
    "t_s",
    "lap_number",
    "stint",
    "compound",
    "tyre_life",
    "running_order",
    "gap_to_leader_s",
}
_CONTROL_REQUIRED = {
    *_RACE_KEYS,
    "t_s",
    "category",
    "flag",
    "message",
    "lap",
}

RACE_CONTROL_IMPACT_COLUMNS = [
    "season",
    "round",
    "race_name",
    "event_id",
    "event_type",
    "deployment_lap",
    "restart_lap",
    "start_t_s",
    "end_t_s",
    "duration_s",
    "event_complete",
    "driver_code",
    "driver_name",
    "team",
    "position_before",
    "position_after",
    "positions_gained",
    "gap_to_leader_before_s",
    "gap_to_leader_after_s",
    "gap_compression_s",
    "stint_before",
    "stint_after",
    "compound_before",
    "compound_after",
    "tyre_life_before",
    "tyre_life_after",
    "stopped_during_event",
    "active_after",
    "eligible",
    "exclusion_reason",
    "confidence",
    "outcome_label",
    "timing_before_offset_s",
    "timing_after_offset_s",
    "methodology_version",
]

_INTEGER_COLUMNS = {
    "season",
    "round",
    "event_id",
    "deployment_lap",
    "restart_lap",
    "position_before",
    "position_after",
    "positions_gained",
    "stint_before",
    "stint_after",
    "tyre_life_before",
    "tyre_life_after",
}
_FLOAT_COLUMNS = {
    "start_t_s",
    "end_t_s",
    "duration_s",
    "gap_to_leader_before_s",
    "gap_to_leader_after_s",
    "gap_compression_s",
    "timing_before_offset_s",
    "timing_after_offset_s",
}
_BOOLEAN_COLUMNS = {
    "event_complete",
    "stopped_during_event",
    "active_after",
    "eligible",
}


@dataclass(frozen=True)
class _Event:
    event_type: str
    start_t_s: float
    start_lap: int | None
    end_t_s: float | None
    end_lap: int | None
    complete: bool
    parse_reason: str | None = None


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
            for column in RACE_CONTROL_IMPACT_COLUMNS
        }
    )


def _require_columns(frame: pd.DataFrame, required: set[str], name: str) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{name} is missing columns: {sorted(missing)}")


def _normalise_message(value: object) -> str:
    return " ".join(str(value).upper().split())


def _event_marker(message: str, flag: str) -> tuple[str, str] | None:
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
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return int(number) if pd.notna(number) else None


def _extract_events(control: pd.DataFrame) -> list[_Event]:
    events: list[_Event] = []
    open_events: dict[str, tuple[float, int | None]] = {}

    for row in control.sort_values("t_s").itertuples(index=False):
        message = _normalise_message(row.message)
        marker = _event_marker(message, _normalise_message(row.flag))
        if marker is None:
            continue
        event_type, action = marker
        t_s = float(row.t_s)
        lap = _optional_int(row.lap)

        if action == "start":
            # A red flag supersedes any live neutralisation. Keep the interrupted
            # period for auditability, but do not publish it as an eligible result.
            if event_type == "Red Flag":
                for interrupted_type in ("Safety Car", "VSC"):
                    interrupted = open_events.pop(interrupted_type, None)
                    if interrupted is not None:
                        events.append(
                            _Event(
                                interrupted_type,
                                interrupted[0],
                                interrupted[1],
                                t_s,
                                lap,
                                False,
                                "Interrupted by red flag",
                            )
                        )
            previous = open_events.get(event_type)
            if previous is not None:
                events.append(
                    _Event(
                        event_type,
                        previous[0],
                        previous[1],
                        t_s,
                        lap,
                        False,
                        "Superseded by another deployment",
                    )
                )
            open_events[event_type] = (t_s, lap)
            continue

        started = open_events.pop(event_type, None)
        if started is not None and t_s > started[0]:
            events.append(_Event(event_type, started[0], started[1], t_s, lap, True))

    for event_type, (start_t_s, start_lap) in open_events.items():
        events.append(
            _Event(
                event_type,
                start_t_s,
                start_lap,
                None,
                None,
                False,
                "No matching end message",
            )
        )
    return sorted(events, key=lambda event: event.start_t_s)


def _snapshot(frame: pd.DataFrame, target_t_s: float, *, before: bool) -> pd.DataFrame:
    candidates = frame.loc[frame["t_s"].le(target_t_s) if before else frame["t_s"].ge(target_t_s)]
    if candidates.empty:
        return candidates
    ordered = candidates.sort_values(["driver_code", "t_s"])
    result = (
        ordered.groupby("driver_code", sort=False).tail(1)
        if before
        else ordered.groupby("driver_code", sort=False).head(1)
    )
    result = result.copy()
    result["capture_offset_s"] = (
        target_t_s - result["t_s"] if before else result["t_s"] - target_t_s
    )
    return result.loc[result["capture_offset_s"].le(MAX_CAPTURE_OFFSET_S)]


def _post_checkpoint_t_s(replay: pd.DataFrame, event: _Event) -> float | None:
    if event.end_t_s is None:
        return None
    if event.event_type != "Safety Car" or event.end_lap is None:
        return event.end_t_s

    leaders = replay.loc[
        replay["t_s"].ge(event.end_t_s)
        & replay["running_order"].eq(1)
        & replay["lap_number"].ge(event.end_lap + 1)
    ]
    if leaders.empty:
        return event.end_t_s
    return float(leaders["t_s"].min())


def _to_int(value: object) -> int | None:
    if pd.isna(value):
        return None
    return int(float(str(value)))


def _outcome_label(eligible: bool, positions_gained: int | None, active_after: bool) -> str:
    if not active_after:
        return "No post-event timing"
    if not eligible or positions_gained is None:
        return "Excluded"
    if positions_gained > 0:
        return "Gained positions"
    if positions_gained < 0:
        return "Lost positions"
    return "Position held"


def _event_rows(
    race_replay: pd.DataFrame,
    event: _Event,
    event_id: int,
) -> list[dict[str, object]]:
    before = _snapshot(race_replay, event.start_t_s, before=True)
    if before.empty:
        return []
    post_t_s = _post_checkpoint_t_s(race_replay, event)
    after = (
        _snapshot(race_replay, post_t_s, before=False)
        if post_t_s is not None
        else race_replay.iloc[0:0].copy()
    )
    after_by_driver = after.set_index("driver_code", drop=False)
    window_end = post_t_s if post_t_s is not None else event.start_t_s
    window = race_replay.loc[race_replay["t_s"].between(event.start_t_s, window_end)]

    rows: list[dict[str, object]] = []
    for pre in before.itertuples(index=False):
        driver = str(pre.driver_code)
        post: pd.Series | None = None
        if driver in after_by_driver.index:
            selected = after_by_driver.loc[driver]
            post = selected.iloc[0] if isinstance(selected, pd.DataFrame) else selected
        active_after = post is not None
        position_before = _to_int(pre.running_order)
        position_after = _to_int(post["running_order"]) if post is not None else None
        positions_gained = (
            position_before - position_after
            if position_before is not None and position_after is not None
            else None
        )
        gap_before = float(pre.gap_to_leader_s) if pd.notna(pre.gap_to_leader_s) else np.nan
        gap_after = (
            float(post["gap_to_leader_s"])
            if post is not None and pd.notna(post["gap_to_leader_s"])
            else np.nan
        )
        driver_window = window.loc[window["driver_code"].eq(driver)]
        stint_before = _to_int(pre.stint)
        stint_after = _to_int(post["stint"]) if post is not None else None
        max_window_stint = pd.to_numeric(driver_window["stint"], errors="coerce").max()
        stopped = bool(
            stint_before is not None
            and pd.notna(max_window_stint)
            and max_window_stint > stint_before
        )

        complete_timing = (
            event.complete
            and active_after
            and position_before is not None
            and position_after is not None
        )
        eligible = bool(complete_timing and event.parse_reason is None)
        exclusion_reason = ""
        if event.parse_reason:
            exclusion_reason = event.parse_reason
        elif not event.complete:
            exclusion_reason = "Incomplete race-control event"
        elif not active_after:
            exclusion_reason = "No post-event timing"
        elif position_before is None or position_after is None:
            exclusion_reason = "Incomplete position timing"

        before_offset = float(pre.capture_offset_s)
        after_offset = float(post["capture_offset_s"]) if post is not None else np.nan
        if not eligible:
            confidence = "Low"
        elif (
            event.event_type in {"Safety Car", "VSC"}
            and before_offset <= HIGH_CONFIDENCE_OFFSET_S
            and after_offset <= HIGH_CONFIDENCE_OFFSET_S
        ):
            confidence = "High"
        else:
            confidence = "Medium"

        rows.append(
            {
                "season": int(pre.season),
                "round": int(pre.round),
                "race_name": str(pre.race_name),
                "event_id": event_id,
                "event_type": event.event_type,
                "deployment_lap": event.start_lap if event.start_lap is not None else pd.NA,
                "restart_lap": event.end_lap if event.end_lap is not None else pd.NA,
                "start_t_s": event.start_t_s,
                "end_t_s": event.end_t_s if event.end_t_s is not None else np.nan,
                "duration_s": (
                    event.end_t_s - event.start_t_s if event.end_t_s is not None else np.nan
                ),
                "event_complete": event.complete,
                "driver_code": driver,
                "driver_name": str(pre.driver_name),
                "team": str(pre.team),
                "position_before": position_before,
                "position_after": position_after,
                "positions_gained": positions_gained,
                "gap_to_leader_before_s": gap_before,
                "gap_to_leader_after_s": gap_after,
                "gap_compression_s": gap_before - gap_after,
                "stint_before": stint_before,
                "stint_after": stint_after,
                "compound_before": str(pre.compound) if pd.notna(pre.compound) else "",
                "compound_after": (
                    str(post["compound"]) if post is not None and pd.notna(post["compound"]) else ""
                ),
                "tyre_life_before": _to_int(pre.tyre_life),
                "tyre_life_after": _to_int(post["tyre_life"]) if post is not None else None,
                "stopped_during_event": stopped,
                "active_after": active_after,
                "eligible": eligible,
                "exclusion_reason": exclusion_reason,
                "confidence": confidence,
                "outcome_label": _outcome_label(eligible, positions_gained, active_after),
                "timing_before_offset_s": before_offset,
                "timing_after_offset_s": after_offset,
                "methodology_version": METHODOLOGY_VERSION,
            }
        )
    return rows


def analyse_race_control_impact(
    replay: pd.DataFrame,
    race_control: pd.DataFrame,
) -> pd.DataFrame:
    """Return one evidence row per driver and neutralisation event."""
    _require_columns(replay, _REPLAY_REQUIRED, "replay")
    _require_columns(race_control, _CONTROL_REQUIRED, "race_control")
    if replay.empty or race_control.empty:
        return _empty_result()

    prepared_replay = replay.copy()
    prepared_control = race_control.copy()
    for frame in (prepared_replay, prepared_control):
        for column in ("season", "round", "t_s"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame.dropna(subset=["season", "round", "t_s"], inplace=True)
    for column in (
        "lap_number",
        "stint",
        "tyre_life",
        "running_order",
        "gap_to_leader_s",
    ):
        prepared_replay[column] = pd.to_numeric(prepared_replay[column], errors="coerce")
    prepared_control["lap"] = pd.to_numeric(prepared_control["lap"], errors="coerce")

    rows: list[dict[str, object]] = []
    for keys, control_race in prepared_control.groupby(_RACE_KEYS, sort=True):
        season, rnd = keys
        replay_race = prepared_replay.loc[
            prepared_replay["season"].eq(season) & prepared_replay["round"].eq(rnd)
        ].copy()
        if replay_race.empty:
            continue
        for event_id, event in enumerate(_extract_events(control_race), start=1):
            rows.extend(_event_rows(replay_race, event, event_id))

    if not rows:
        return _empty_result()
    result = pd.DataFrame(rows, columns=RACE_CONTROL_IMPACT_COLUMNS)
    for column in _INTEGER_COLUMNS:
        result[column] = pd.to_numeric(result[column], errors="coerce").astype("Int64")
    for column in _FLOAT_COLUMNS:
        result[column] = pd.to_numeric(result[column], errors="coerce").astype("float64")
    for column in _BOOLEAN_COLUMNS:
        result[column] = result[column].astype("boolean")
    for column in (
        set(RACE_CONTROL_IMPACT_COLUMNS) - _INTEGER_COLUMNS - _FLOAT_COLUMNS - _BOOLEAN_COLUMNS
    ):
        result[column] = result[column].astype("string")
    return result.sort_values(["season", "round", "event_id", "position_before"]).reset_index(
        drop=True
    )
