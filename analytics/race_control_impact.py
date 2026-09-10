"""Observed position and relative-gap changes across race neutralisations.

Official Safety Car, VSC and red-flag messages are paired with a small state
machine. Driver state at deployment is compared with the third leader crossing
after the end signal. Publication requires two complete green reference-leader
laps, not a claim that every driver's recovery is independently observed.
The metric is descriptive evidence, not a causal strategy estimate.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

METHODOLOGY_VERSION = "race-control-impact-v2"
MAX_CAPTURE_OFFSET_S = 3.0
HIGH_CONFIDENCE_OFFSET_S = 1.5
DEFAULT_MIN_EVENT_DRIVERS = 12
MIN_TIME_COMPARABLE_DRIVERS = 5
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
    "gap_to_leader_before_s",
    "gap_to_leader_after_s",
    "raw_gap_gain_s",
    "field_adjusted_gap_gain_s",
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
    "stop_count",
    "tyre_changed_during_suspension",
    "active_after",
    "eligible",
    "exclusion_reason",
    "confidence",
    "outcome_label",
    "timing_before_offset_s",
    "timing_after_offset_s",
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
}
_IMPACT_FLOAT = {
    "gap_to_leader_before_s",
    "gap_to_leader_after_s",
    "raw_gap_gain_s",
    "field_adjusted_gap_gain_s",
    "timing_before_offset_s",
    "timing_after_offset_s",
}
_IMPACT_BOOLEAN = {
    "lap_deficit_changed",
    "pitted_during_intervention",
    "pitted_during_recovery",
    "tyre_changed_during_suspension",
    "active_after",
    "eligible",
    "time_eligible",
}


@dataclass(frozen=True)
class RaceControlImpactResult:
    """Event-level summary and driver-level supporting evidence."""

    events: pd.DataFrame
    evidence: pd.DataFrame


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
    )


def _require_columns(frame: pd.DataFrame, required: set[str], name: str) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{name} is missing columns: {sorted(missing)}")


def _normalise(value: object) -> str:
    return " ".join(str(value).upper().split())


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
        marker = _marker(_normalise(row.message), _normalise(row.flag))
        if marker is None:
            continue
        event_type, action = marker
        t_s, lap = float(row.t_s), _optional_int(row.lap)
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
    return snapshot.loc[snapshot["capture_offset_s"].le(MAX_CAPTURE_OFFSET_S)]


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
        0 <= start - starts[0] <= MAX_CAPTURE_OFFSET_S
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


def _to_int(value: object) -> int | None:
    if pd.isna(value):
        return None
    return int(float(str(value)))


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
        raw_gap_gain = (
            gap_before - gap_after
            if event.event_type != "Red Flag"
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
            and before_offset <= MAX_CAPTURE_OFFSET_S
            and after_offset <= MAX_CAPTURE_OFFSET_S
        )
        reason = event_reason
        if not active_after:
            reason = "No post-event timing"
        elif position_before is None or position_after is None:
            reason = "Incomplete position timing"
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
                "gap_to_leader_before_s": gap_before,
                "gap_to_leader_after_s": gap_after,
                "raw_gap_gain_s": raw_gap_gain,
                "field_adjusted_gap_gain_s": np.nan,
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
                "stop_count": stop_count,
                "tyre_changed_during_suspension": tyre_changed_red,
                "active_after": active_after,
                "eligible": driver_eligible,
                "exclusion_reason": "" if driver_eligible else reason,
                "confidence": confidence,
                "outcome_label": _outcome(driver_eligible, positions_gained, active_after),
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
    *,
    min_event_drivers: int = DEFAULT_MIN_EVENT_DRIVERS,
) -> RaceControlImpactResult:
    """Build event summaries and driver evidence for every exact neutralisation pair."""
    _require_columns(replay, _REPLAY_REQUIRED, "replay")
    _require_columns(race_control, _CONTROL_REQUIRED, "race_control")
    _require_columns(laps, _LAPS_REQUIRED, "laps")
    if min_event_drivers < 1:
        raise ValueError("min_event_drivers must be at least one")
    if race_control.empty:
        return _empty_result()

    replay = replay.copy()
    race_control = race_control.copy()
    laps = laps.copy()
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

    event_rows: list[dict[str, object]] = []
    evidence_rows: list[dict[str, object]] = []
    grouped = race_control.dropna(subset=[*_RACE_KEYS, "t_s"]).groupby(_RACE_KEYS, sort=True)
    for keys, control_race in grouped:
        season, rnd = (int(keys[0]), int(keys[1]))
        replay_race = replay.loc[replay["season"].eq(season) & replay["round"].eq(rnd)]
        laps_race = laps.loc[laps["season"].eq(season) & laps["round"].eq(rnd)]
        events = _extract_events(control_race)
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
            evidence_rows.extend(driver_rows)
            eligible_driver_rows = [row for row in driver_rows if bool(row["eligible"])]
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
                        float(str(row["positions_gained"] or 0)) > 0 for row in eligible_driver_rows
                    ),
                    "position_loser_count": sum(
                        float(str(row["positions_gained"] or 0)) < 0 for row in eligible_driver_rows
                    ),
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
    if not evidence_frame.empty:
        evidence_frame = evidence_frame.sort_values(
            ["season", "round", "event_number", "position_before"]
        ).reset_index(drop=True)
    return RaceControlImpactResult(
        events=events_frame.sort_values(["season", "round", "event_number"]).reset_index(drop=True),
        evidence=evidence_frame,
    )
