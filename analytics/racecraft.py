"""Observed conversion of sustained close-running battle episodes.

This module measures what happened after a car spent meaningful green-flag
time directly behind another car.  It deliberately does not call the result a
driver-skill score: reconstructed gaps cannot observe DRS eligibility, car and
tyre advantage, team orders, damage, or opponent quality.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import sqrt
from typing import Any, cast

import numpy as np
import pandas as pd

METHODOLOGY_VERSION = "racecraft-v2-pit-context"
PRESSURE_GAP_S = 1.0
CONTACT_GAP_S = 1.5
RELEASE_GAP_S = 2.0
MIN_PRESSURE_S = 10.0
RELEASE_CONFIRM_S = 15.0
MAX_TICK_GAP_S = 3.0
PASS_MATCH_S = 3.0
MIN_RATE_OPPORTUNITIES = 5

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
    "running_order",
    "gap_to_ahead_s",
    "track_status",
    "is_pit_boundary",
}
_OVERTAKE_REQUIRED = {
    *_RACE_KEYS,
    "t_s",
    "passer_code",
    "passed_code",
    "confidence",
    "reason",
}

BATTLE_COLUMNS = [
    "season",
    "round",
    "race_name",
    "battle_id",
    "battle_number",
    "attacker_code",
    "attacker_name",
    "attacker_team",
    "defender_code",
    "defender_name",
    "defender_team",
    "same_team",
    "start_t_s",
    "end_t_s",
    "duration_s",
    "pressure_seconds",
    "contact_seconds",
    "start_lap",
    "end_lap",
    "laps_spanned",
    "position_contested",
    "valid_samples",
    "pressure_samples",
    "coverage_pct",
    "same_lap_deficit_share_pct",
    "min_gap_s",
    "median_gap_s",
    "outcome",
    "terminal_reason",
    "converted",
    "defender_retained",
    "pass_t_s",
    "pass_lap",
    "time_to_pass_s",
    "overtake_confidence",
    "overtake_reason",
    "quick_reversal",
    "reversal_t_s",
    "eligible",
    "exclusion_reason",
    "confidence",
    "pressure_gap_threshold_s",
    "minimum_pressure_s",
    "methodology_version",
]

SUMMARY_COLUMNS = [
    "season",
    "round",
    "race_name",
    "driver_code",
    "driver_name",
    "team",
    "attacking_opportunities",
    "converted_opportunities",
    "attacks_defended",
    "attack_conversion_pct",
    "attack_conversion_p05_pct",
    "attack_conversion_p95_pct",
    "attack_pressure_s",
    "distinct_defenders",
    "median_time_to_pass_s",
    "defensive_opportunities",
    "defences_held",
    "passes_conceded",
    "defence_hold_pct",
    "defence_hold_p05_pct",
    "defence_hold_p95_pct",
    "defensive_pressure_s",
    "distinct_attackers",
    "interrupted_attacks",
    "unresolved_attacks",
    "interrupted_defences",
    "unresolved_defences",
    "quick_reversals_made",
    "quick_reversals_conceded",
    "longest_battle_s",
    "offense_eligible",
    "defense_eligible",
    "offense_exclusion_reason",
    "defense_exclusion_reason",
    "offense_confidence",
    "defense_confidence",
    "confidence",
    "methodology_version",
]

_BATTLE_INTEGER = {
    "season",
    "round",
    "battle_number",
    "start_lap",
    "end_lap",
    "laps_spanned",
    "position_contested",
    "valid_samples",
    "pressure_samples",
    "pass_lap",
}
_BATTLE_FLOAT = {
    "start_t_s",
    "end_t_s",
    "duration_s",
    "pressure_seconds",
    "contact_seconds",
    "coverage_pct",
    "same_lap_deficit_share_pct",
    "min_gap_s",
    "median_gap_s",
    "pass_t_s",
    "time_to_pass_s",
    "overtake_confidence",
    "reversal_t_s",
    "pressure_gap_threshold_s",
    "minimum_pressure_s",
}
_BATTLE_BOOLEAN = {"same_team", "converted", "defender_retained", "quick_reversal", "eligible"}
_SUMMARY_INTEGER = {
    "season",
    "round",
    "attacking_opportunities",
    "converted_opportunities",
    "attacks_defended",
    "distinct_defenders",
    "defensive_opportunities",
    "defences_held",
    "passes_conceded",
    "distinct_attackers",
    "interrupted_attacks",
    "unresolved_attacks",
    "interrupted_defences",
    "unresolved_defences",
    "quick_reversals_made",
    "quick_reversals_conceded",
}
_SUMMARY_FLOAT = {
    "attack_conversion_pct",
    "attack_conversion_p05_pct",
    "attack_conversion_p95_pct",
    "attack_pressure_s",
    "median_time_to_pass_s",
    "defence_hold_pct",
    "defence_hold_p05_pct",
    "defence_hold_p95_pct",
    "defensive_pressure_s",
    "longest_battle_s",
}
_SUMMARY_BOOLEAN = {"offense_eligible", "defense_eligible"}


@dataclass(frozen=True)
class RacecraftResult:
    """Battle-level evidence and driver-race summaries."""

    battles: pd.DataFrame
    summary: pd.DataFrame


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


def _empty_result() -> RacecraftResult:
    return RacecraftResult(
        battles=_typed_empty(BATTLE_COLUMNS, _BATTLE_INTEGER, _BATTLE_FLOAT, _BATTLE_BOOLEAN),
        summary=_typed_empty(SUMMARY_COLUMNS, _SUMMARY_INTEGER, _SUMMARY_FLOAT, _SUMMARY_BOOLEAN),
    )


def _require_columns(frame: pd.DataFrame, required: set[str], name: str) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{name} is missing columns: {sorted(missing)}")


def _prepare_replay(replay: pd.DataFrame) -> pd.DataFrame:
    out = replay.copy()
    numeric = [
        "season",
        "round",
        "t_s",
        "lap_number",
        "lap_progress",
        "stint",
        "running_order",
        "gap_to_ahead_s",
    ]
    for column in numeric:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out[numeric] = out[numeric].replace([np.inf, -np.inf], np.nan)
    out = out.dropna(subset=[*_RACE_KEYS, "driver_code", "t_s", "running_order"])
    out = out.drop_duplicates([*_RACE_KEYS, "t_s", "driver_code"], keep="last")
    out["track_status"] = out["track_status"].astype("string").str.strip()
    out["is_pit_boundary"] = out["is_pit_boundary"].fillna(False).astype(bool)
    return out.sort_values([*_RACE_KEYS, "t_s", "running_order"]).reset_index(drop=True)


def _prepare_overtakes(overtakes: pd.DataFrame) -> pd.DataFrame:
    out = overtakes.copy()
    for column in ("season", "round", "t_s", "confidence"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out = out.dropna(subset=[*_RACE_KEYS, "t_s", "passer_code", "passed_code"])
    duplicate = out.duplicated([*_RACE_KEYS, "t_s", "passer_code", "passed_code"], keep=False)
    if duplicate.any():
        raise ValueError("overtakes contains duplicate directional pass rows")
    return out.sort_values([*_RACE_KEYS, "t_s"]).reset_index(drop=True)


def _adjacency(replay: pd.DataFrame) -> pd.DataFrame:
    order_keys = [*_RACE_KEYS, "t_s", "running_order"]
    if replay.duplicated(order_keys).any():
        raise ValueError("replay contains duplicate running positions at a race tick")
    out = replay.sort_values(order_keys).copy()
    groups = out.groupby([*_RACE_KEYS, "t_s"], sort=False)
    for source, target in {
        "driver_code": "defender_code",
        "driver_name": "defender_name",
        "team": "defender_team",
        "lap_number": "defender_lap_number",
        "lap_progress": "defender_lap_progress",
        "stint": "defender_stint",
        "track_status": "defender_track_status",
        "is_pit_boundary": "defender_pit_boundary",
    }.items():
        out[target] = groups[source].shift(1)
    return out.sort_values([*_RACE_KEYS, "driver_code", "t_s"])


def _tick_interval(driver_ticks: pd.DataFrame) -> float:
    intervals = driver_ticks["t_s"].diff()
    usable = intervals.loc[intervals.gt(0) & intervals.le(MAX_TICK_GAP_S)]
    return float(usable.median()) if not usable.empty else 1.0


def _same_lap_deficit(row: Mapping[str, Any]) -> bool:
    values = [
        row["lap_number"],
        row["lap_progress"],
        row["defender_lap_number"],
        row["defender_lap_progress"],
    ]
    if any(pd.isna(value) for value in values):
        return False
    attacker_progress = float(row["lap_number"]) - 1 + float(row["lap_progress"])
    defender_progress = float(row["defender_lap_number"]) - 1 + float(row["defender_lap_progress"])
    difference = defender_progress - attacker_progress
    return -0.05 <= difference <= 0.25


def _green(row: Mapping[str, Any]) -> bool:
    return bool(row["track_status"] == "1" and row["defender_track_status"] == "1")


def _contact(row: Mapping[str, Any], contact_gap_s: float) -> bool:
    gap = row["gap_to_ahead_s"]
    return (
        isinstance(row["defender_code"], str)
        and _green(row)
        and _same_lap_deficit(row)
        and pd.notna(gap)
        and 0 < float(gap) <= contact_gap_s
        and float(row["lap_number"]) > 1
        and float(row["lap_progress"]) < 1
        and float(row["t_s"]) >= 60
        and not bool(row["is_pit_boundary"])
        and not bool(row["defender_pit_boundary"])
    )


def _match_pass(
    overtakes: pd.DataFrame,
    used: set[int],
    *,
    attacker: str,
    defender: str,
    start_t: float,
    end_t: float,
    pass_match_s: float,
) -> tuple[int, pd.Series] | None:
    candidates = overtakes.loc[
        overtakes["passer_code"].eq(attacker)
        & overtakes["passed_code"].eq(defender)
        & overtakes["t_s"].between(start_t, end_t + pass_match_s)
    ]
    for index, row in candidates.iterrows():
        if index not in used:
            return int(index), row
    return None


def _quick_reversal(
    overtakes: pd.DataFrame, pass_row: pd.Series, attacker: str, defender: str
) -> tuple[bool, float]:
    reverse = overtakes.loc[
        overtakes["passer_code"].eq(defender)
        & overtakes["passed_code"].eq(attacker)
        & overtakes["t_s"].gt(pass_row["t_s"])
        & overtakes["t_s"].le(float(pass_row["t_s"]) + 60)
    ]
    if reverse.empty:
        return False, np.nan
    return True, float(reverse.iloc[0]["t_s"])


def _episode_row(
    state: dict[str, object],
    *,
    end_t: float,
    terminal: str,
    overtakes: pd.DataFrame,
    used_passes: set[int],
    pressure_gap_s: float,
    min_pressure_s: float,
    pass_match_s: float,
) -> dict[str, object] | None:
    observations = state["observations"]
    assert isinstance(observations, list)
    if not observations:
        return None
    frame = pd.DataFrame(observations)
    tick_s = cast(float, state["tick_s"])
    pressure = frame.loc[frame["gap_to_ahead_s"].le(pressure_gap_s)]
    contact = frame.loc[frame["gap_to_ahead_s"].le(cast(float, state["contact_gap_s"]))]
    pressure_seconds = len(pressure) * tick_s
    contact_seconds = len(contact) * tick_s
    start_t = cast(float, state["start_t"])
    duration = max(tick_s, end_t - start_t + tick_s)
    matched = _match_pass(
        overtakes,
        used_passes,
        attacker=str(state["attacker_code"]),
        defender=str(state["defender_code"]),
        start_t=start_t,
        end_t=end_t,
        pass_match_s=pass_match_s,
    )
    if matched is not None and terminal not in {"pit_boundary", "non_green"}:
        pass_index, pass_row = matched
        used_passes.add(pass_index)
        outcome = "Converted"
        terminal_reason = "confirmed_overtake"
        converted = True
        retained = False
        pass_t = float(pass_row["t_s"])
        nearest = frame.iloc[(frame["t_s"] - pass_t).abs().argsort()[:1]]
        pass_lap: object = int(nearest.iloc[0]["lap_number"])
        overtake_confidence = float(pass_row["confidence"])
        overtake_reason = str(pass_row["reason"])
        quick_reversal, reversal_t = _quick_reversal(
            overtakes,
            pass_row,
            str(state["attacker_code"]),
            str(state["defender_code"]),
        )
    else:
        converted = False
        pass_t = np.nan
        pass_lap = pd.NA
        overtake_confidence = np.nan
        overtake_reason = ""
        quick_reversal = False
        reversal_t = np.nan
        if terminal == "gap_released":
            outcome, terminal_reason, retained = "Defended", "gap_opened", True
        elif terminal in {"pit_boundary", "non_green", "third_car_change"}:
            outcome, terminal_reason, retained = "Interrupted", terminal, False
        else:
            outcome, terminal_reason, retained = "Unresolved", terminal, False

    valid_samples = cast(int, state["valid_samples"])
    same_lap_samples = cast(int, state["same_lap_samples"])
    same_lap_share = 100.0 * same_lap_samples / valid_samples
    coverage = min(100.0, 100.0 * valid_samples * tick_s / duration)
    sufficient = pressure_seconds >= min_pressure_s and same_lap_share >= 80 and coverage >= 80
    resolved = outcome in {"Converted", "Defended"}
    eligible = sufficient and resolved
    if pressure_seconds < min_pressure_s:
        exclusion = "insufficient_sustained_pressure"
    elif same_lap_share < 80:
        exclusion = "lap_deficit_changed"
    elif coverage < 80:
        exclusion = "under_covered_episode"
    elif not resolved:
        exclusion = terminal_reason
    else:
        exclusion = ""
    same_team = str(state["attacker_team"]) == str(state["defender_team"])
    strong_pass = outcome != "Converted" or overtake_confidence >= 0.85
    confidence = (
        "high"
        if eligible
        and pressure_seconds >= 20
        and coverage >= 95
        and same_lap_share >= 90
        and strong_pass
        and not same_team
        else "medium"
        if eligible
        else "low"
        if sufficient
        else "insufficient"
    )
    start_lap = int(frame.iloc[0]["lap_number"])
    end_lap = int(frame.iloc[-1]["lap_number"])
    return {
        "season": state["season"],
        "round": state["round"],
        "race_name": state["race_name"],
        "battle_id": "",
        "battle_number": 0,
        "attacker_code": state["attacker_code"],
        "attacker_name": state["attacker_name"],
        "attacker_team": state["attacker_team"],
        "defender_code": state["defender_code"],
        "defender_name": state["defender_name"],
        "defender_team": state["defender_team"],
        "same_team": same_team,
        "start_t_s": start_t,
        "end_t_s": end_t,
        "duration_s": duration,
        "pressure_seconds": pressure_seconds,
        "contact_seconds": contact_seconds,
        "start_lap": start_lap,
        "end_lap": end_lap,
        "laps_spanned": end_lap - start_lap + 1,
        "position_contested": state["position_contested"],
        "valid_samples": valid_samples,
        "pressure_samples": len(pressure),
        "coverage_pct": coverage,
        "same_lap_deficit_share_pct": same_lap_share,
        "min_gap_s": float(frame["gap_to_ahead_s"].min()),
        "median_gap_s": float(frame["gap_to_ahead_s"].median()),
        "outcome": outcome,
        "terminal_reason": terminal_reason,
        "converted": converted,
        "defender_retained": retained,
        "pass_t_s": pass_t,
        "pass_lap": pass_lap,
        "time_to_pass_s": pass_t - start_t if converted else np.nan,
        "overtake_confidence": overtake_confidence,
        "overtake_reason": overtake_reason,
        "quick_reversal": quick_reversal,
        "reversal_t_s": reversal_t,
        "eligible": eligible,
        "exclusion_reason": exclusion,
        "confidence": confidence,
        "pressure_gap_threshold_s": pressure_gap_s,
        "minimum_pressure_s": min_pressure_s,
        "methodology_version": METHODOLOGY_VERSION,
    }


def _new_state(row: Mapping[str, Any], tick_s: float, contact_gap_s: float) -> dict[str, object]:
    return {
        "season": row["season"],
        "round": row["round"],
        "race_name": row["race_name"],
        "attacker_code": row["driver_code"],
        "attacker_name": row["driver_name"],
        "attacker_team": row["team"],
        "defender_code": row["defender_code"],
        "defender_name": row["defender_name"],
        "defender_team": row["defender_team"],
        "position_contested": int(row["running_order"] - 1),
        "start_t": float(row["t_s"]),
        "last_t": float(row["t_s"]),
        "release_start": None,
        "tick_s": tick_s,
        "contact_gap_s": contact_gap_s,
        "valid_samples": 1,
        "same_lap_samples": 1,
        "observations": [],
    }


def _observation(row: Mapping[str, Any]) -> dict[str, object]:
    return {
        "t_s": float(row["t_s"]),
        "lap_number": int(row["lap_number"]),
        "gap_to_ahead_s": float(row["gap_to_ahead_s"]),
        "same_lap_deficit": _same_lap_deficit(row),
    }


def _detect_battles(
    replay: pd.DataFrame,
    overtakes: pd.DataFrame,
    *,
    pressure_gap_s: float,
    contact_gap_s: float,
    release_gap_s: float,
    min_pressure_s: float,
    release_confirm_s: float,
    pass_match_s: float,
) -> pd.DataFrame:
    adjacency = _adjacency(replay)
    rows: list[dict[str, object]] = []
    used_passes: set[int] = set()
    for race_key, race in adjacency.groupby(_RACE_KEYS, sort=True):
        race_overtakes = overtakes.loc[
            overtakes["season"].eq(race_key[0]) & overtakes["round"].eq(race_key[1])
        ]
        for _, driver_ticks in race.groupby("driver_code", sort=True):
            driver_ticks = driver_ticks.sort_values("t_s")
            tick_s = _tick_interval(driver_ticks)
            state: dict[str, object] | None = None
            records = cast(list[dict[str, Any]], driver_ticks.to_dict(orient="records"))
            for row in records:
                now = float(row["t_s"])
                is_contact = _contact(row, contact_gap_s)
                if state is None:
                    if is_contact:
                        state = _new_state(row, tick_s, contact_gap_s)
                        observations = state["observations"]
                        assert isinstance(observations, list)
                        observations.append(_observation(row))
                    continue

                last_t = cast(float, state["last_t"])
                same_pair = row["defender_code"] == state["defender_code"]
                terminal = ""
                if now - last_t > MAX_TICK_GAP_S:
                    terminal = "feed_gap"
                elif not same_pair:
                    terminal = "third_car_change"
                elif not _green(row):
                    terminal = "non_green"
                elif bool(row["is_pit_boundary"]) or bool(row["defender_pit_boundary"]):
                    terminal = "pit_boundary"
                if terminal:
                    episode = _episode_row(
                        state,
                        end_t=last_t,
                        terminal=terminal,
                        overtakes=race_overtakes,
                        used_passes=used_passes,
                        pressure_gap_s=pressure_gap_s,
                        min_pressure_s=min_pressure_s,
                        pass_match_s=pass_match_s,
                    )
                    if episode is not None:
                        rows.append(episode)
                    state = None
                    if is_contact:
                        state = _new_state(row, tick_s, contact_gap_s)
                        observations = state["observations"]
                        assert isinstance(observations, list)
                        observations.append(_observation(row))
                    continue

                gap = row["gap_to_ahead_s"]
                state["valid_samples"] = cast(int, state["valid_samples"]) + 1
                if _same_lap_deficit(row):
                    state["same_lap_samples"] = cast(int, state["same_lap_samples"]) + 1
                if pd.notna(gap) and 0 < float(gap) <= contact_gap_s and _same_lap_deficit(row):
                    observations = state["observations"]
                    assert isinstance(observations, list)
                    observations.append(_observation(row))
                    state["release_start"] = None
                elif pd.notna(gap) and float(gap) > release_gap_s:
                    if state["release_start"] is None:
                        state["release_start"] = now
                    elif now - cast(float, state["release_start"]) >= release_confirm_s:
                        episode = _episode_row(
                            state,
                            end_t=now,
                            terminal="gap_released",
                            overtakes=race_overtakes,
                            used_passes=used_passes,
                            pressure_gap_s=pressure_gap_s,
                            min_pressure_s=min_pressure_s,
                            pass_match_s=pass_match_s,
                        )
                        if episode is not None:
                            rows.append(episode)
                        state = None
                        continue
                state["last_t"] = now
            if state is not None:
                episode = _episode_row(
                    state,
                    end_t=cast(float, state["last_t"]),
                    terminal="race_or_feed_end",
                    overtakes=race_overtakes,
                    used_passes=used_passes,
                    pressure_gap_s=pressure_gap_s,
                    min_pressure_s=min_pressure_s,
                    pass_match_s=pass_match_s,
                )
                if episode is not None:
                    rows.append(episode)
    if not rows:
        return _typed_empty(BATTLE_COLUMNS, _BATTLE_INTEGER, _BATTLE_FLOAT, _BATTLE_BOOLEAN)
    battles = pd.DataFrame(rows, columns=BATTLE_COLUMNS).sort_values(
        [*_RACE_KEYS, "start_t_s", "attacker_code", "defender_code"]
    )
    battles["battle_number"] = battles.groupby(_RACE_KEYS).cumcount() + 1
    battles["battle_id"] = (
        battles["season"].astype(int).astype(str)
        + "-R"
        + battles["round"].astype(int).astype(str).str.zfill(2)
        + "-B"
        + battles["battle_number"].astype(int).astype(str).str.zfill(4)
    )
    return battles.loc[:, BATTLE_COLUMNS]


def _wilson(successes: int, total: int) -> tuple[float, float]:
    if total == 0:
        return np.nan, np.nan
    z = 1.6448536269514722
    proportion = successes / total
    denominator = 1 + z**2 / total
    centre = (proportion + z**2 / (2 * total)) / denominator
    margin = z / denominator * sqrt(proportion * (1 - proportion) / total + z**2 / (4 * total**2))
    return 100 * (centre - margin), 100 * (centre + margin)


def _rate_confidence(episodes: pd.DataFrame) -> tuple[bool, str, str]:
    count = len(episodes)
    if count < MIN_RATE_OPPORTUNITIES:
        return False, "insufficient_opportunities", "low" if count else "insufficient"
    high_share = float(episodes["confidence"].eq("high").mean())
    return True, "", "high" if count >= 10 and high_share >= 0.80 else "medium"


def _summarise(replay: pd.DataFrame, battles: pd.DataFrame) -> pd.DataFrame:
    roster = replay.loc[:, [*_RACE_KEYS, "race_name", "driver_code", "driver_name", "team"]]
    roster = roster.drop_duplicates([*_RACE_KEYS, "driver_code"])
    rows: list[dict[str, object]] = []
    for driver in roster.itertuples(index=False):
        attacks_all = battles.loc[
            battles["season"].eq(driver.season)
            & battles["round"].eq(driver.round)
            & battles["attacker_code"].eq(driver.driver_code)
        ]
        defences_all = battles.loc[
            battles["season"].eq(driver.season)
            & battles["round"].eq(driver.round)
            & battles["defender_code"].eq(driver.driver_code)
        ]
        attacks = attacks_all.loc[attacks_all["eligible"]]
        defences = defences_all.loc[defences_all["eligible"]]
        conversions = attacks.loc[attacks["converted"]]
        holds = defences.loc[defences["defender_retained"]]
        offense_eligible, offense_reason, offense_confidence = _rate_confidence(attacks)
        defense_eligible, defense_reason, defense_confidence = _rate_confidence(defences)
        attack_lo, attack_hi = _wilson(len(conversions), len(attacks))
        defense_lo, defense_hi = _wilson(len(holds), len(defences))
        ranks = {"insufficient": 0, "low": 1, "medium": 2, "high": 3}
        combined = min((offense_confidence, defense_confidence), key=lambda value: ranks[value])
        rows.append(
            {
                "season": driver.season,
                "round": driver.round,
                "race_name": driver.race_name,
                "driver_code": driver.driver_code,
                "driver_name": driver.driver_name,
                "team": driver.team,
                "attacking_opportunities": len(attacks),
                "converted_opportunities": len(conversions),
                "attacks_defended": len(attacks) - len(conversions),
                "attack_conversion_pct": 100 * len(conversions) / len(attacks)
                if offense_eligible
                else np.nan,
                "attack_conversion_p05_pct": attack_lo if offense_eligible else np.nan,
                "attack_conversion_p95_pct": attack_hi if offense_eligible else np.nan,
                "attack_pressure_s": float(attacks["pressure_seconds"].sum()),
                "distinct_defenders": int(attacks["defender_code"].nunique()),
                "median_time_to_pass_s": float(conversions["time_to_pass_s"].median())
                if not conversions.empty
                else np.nan,
                "defensive_opportunities": len(defences),
                "defences_held": len(holds),
                "passes_conceded": len(defences) - len(holds),
                "defence_hold_pct": 100 * len(holds) / len(defences)
                if defense_eligible
                else np.nan,
                "defence_hold_p05_pct": defense_lo if defense_eligible else np.nan,
                "defence_hold_p95_pct": defense_hi if defense_eligible else np.nan,
                "defensive_pressure_s": float(defences["pressure_seconds"].sum()),
                "distinct_attackers": int(defences["attacker_code"].nunique()),
                "interrupted_attacks": int(attacks_all["outcome"].eq("Interrupted").sum()),
                "unresolved_attacks": int(attacks_all["outcome"].eq("Unresolved").sum()),
                "interrupted_defences": int(defences_all["outcome"].eq("Interrupted").sum()),
                "unresolved_defences": int(defences_all["outcome"].eq("Unresolved").sum()),
                "quick_reversals_made": int(attacks_all["quick_reversal"].sum()),
                "quick_reversals_conceded": int(defences_all["quick_reversal"].sum()),
                "longest_battle_s": float(
                    pd.concat([attacks_all["duration_s"], defences_all["duration_s"]]).max()
                )
                if not attacks_all.empty or not defences_all.empty
                else np.nan,
                "offense_eligible": offense_eligible,
                "defense_eligible": defense_eligible,
                "offense_exclusion_reason": offense_reason,
                "defense_exclusion_reason": defense_reason,
                "offense_confidence": offense_confidence,
                "defense_confidence": defense_confidence,
                "confidence": combined,
                "methodology_version": METHODOLOGY_VERSION,
            }
        )
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS).sort_values(
        ["season", "round", "driver_code"]
    )


def analyse_racecraft_battles(
    replay: pd.DataFrame,
    overtakes: pd.DataFrame,
    *,
    pressure_gap_s: float = PRESSURE_GAP_S,
    contact_gap_s: float = CONTACT_GAP_S,
    release_gap_s: float = RELEASE_GAP_S,
    min_pressure_s: float = MIN_PRESSURE_S,
    release_confirm_s: float = RELEASE_CONFIRM_S,
    pass_match_s: float = PASS_MATCH_S,
) -> RacecraftResult:
    """Detect close-running episodes and summarise observed conversion."""
    _require_columns(replay, _REPLAY_REQUIRED, "replay")
    _require_columns(overtakes, _OVERTAKE_REQUIRED, "overtakes")
    if not 0 < pressure_gap_s <= contact_gap_s < release_gap_s:
        raise ValueError("require 0 < pressure_gap_s <= contact_gap_s < release_gap_s")
    if min_pressure_s <= 0 or release_confirm_s <= 0 or pass_match_s < 0:
        raise ValueError("duration thresholds must be positive (pass match may be zero)")
    if replay.empty:
        return _empty_result()
    prepared = _prepare_replay(replay)
    passes = _prepare_overtakes(overtakes)
    battles = _detect_battles(
        prepared,
        passes,
        pressure_gap_s=pressure_gap_s,
        contact_gap_s=contact_gap_s,
        release_gap_s=release_gap_s,
        min_pressure_s=min_pressure_s,
        release_confirm_s=release_confirm_s,
        pass_match_s=pass_match_s,
    )
    summary = _summarise(prepared, battles)
    return RacecraftResult(
        battles=battles.reset_index(drop=True), summary=summary.reset_index(drop=True)
    )
