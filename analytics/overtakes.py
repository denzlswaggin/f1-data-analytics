"""Overtake & battle detection over the resampled race replay.

The replay mart (``analytics.replay``) already ranks the whole field every tick
(``running_order``, a dense 1..N) and carries each car's x/y and its interval to
the car ahead. An **on-track overtake** is a clean, single-position swap between
two cars that are *physically next to each other*: the car directly behind takes
the position and holds it. Reading from the already-built ``marts.race_replay``
means the detected passes line up exactly with what the animation shows.

The one subtlety is telling an on-track pass from a **pit-cycle** position change.
The gap here is projected from *lap progress*, so when a car pits its progress
plateaus and the progress-gap to whoever is catching it momentarily collapses to
~0 — a pit pass *looks* close in time. What separates the two is **physical
distance**: two cars that really swapped on track are a car-length apart at the
moment of the pass, whereas the pitting car sits in the pit lane, far away. So
proximity is measured in x/y (relative to the circuit's extent), not in seconds.

All logic is pure (synthetic frames, no warehouse) so it unit-tests without the
dbt/telemetry extras, exactly like ``analytics.replay``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from ingestion.logging import get_logger

log = get_logger(__name__)

# Secondary time gate: the interval between the two cars just after the pass must
# be under this (seconds). On-track passes finish nose-to-tail; a loose default.
_BATTLE_GAP_S = 2.0
# The passer must stay ahead of the passed car for this long (seconds) after the
# swap — rejects rank-boundary flicker where the order oscillates for a tick.
_PERSIST_S = 3.0
# Skip the first few seconds: the standing-start running order at t≈0 is cosmetic
# (all cars share lap-progress 0 and are ordered by a tie-break), so ignore it.
_START_GUARD_S = 3.0
# Physical-proximity gate as a fraction of the circuit's bounding-box diagonal.
# Two cars closer than this at the completion tick count as an on-track pass; a
# pitting car is displaced well beyond it. Circuit-relative so it travels between
# tracks; ~2% of the extent is a few tens of metres.
_PROXIMITY_FRAC = 0.02
# A ranking update can briefly omit one of the two cars while timing data catches
# up. Look through that short incomplete interval instead of requiring both sides
# of the swap to appear in consecutive replay ticks.
_TRANSITION_S = 2.0

_COLUMNS = [
    "t_s",
    "for_position",
    "passer_code",
    "passed_code",
    "gap_at_pass_s",
    "confidence",
    "evidence",
    "reason",
]


def _stays_ahead(
    order_a: dict[str, np.ndarray],
    passer: str,
    passed: str,
    ticks: np.ndarray,
    i: int,
    persist_s: float,
) -> bool:
    """True if ``passer`` never falls back behind ``passed`` within ``persist_s``.

    Only ticks where both cars have a finite running order are checked (a car that
    retires during the window doesn't invalidate a completed pass).
    """
    oa = order_a.get(passer)
    ob = order_a.get(passed)
    if oa is None or ob is None:
        return True
    t_end = ticks[i] + persist_s
    for k in range(i, len(ticks)):
        if ticks[k] > t_end:
            break
        a, b = oa[k], ob[k]
        if np.isfinite(a) and np.isfinite(b) and a >= b:
            return False
    return True


def _transition_anchor(
    holder_arr: np.ndarray,
    order_a: dict[str, np.ndarray],
    ticks: np.ndarray,
    i: int,
    jp: int,
    jp1: int,
    position: int,
    passer: str,
    passed: str,
    transition_s: float,
) -> int | None:
    """Return the pre-pass tick for a clean adjacent short transition.

    Timing feeds occasionally omit one car's running order for a tick while a
    swap resolves. Such an incomplete tick is safe to bridge, but a finite order
    outside the two contested places is not: that is a multi-car/distant change,
    not a clean adjacent pass.
    """
    passer_order = order_a[passer]
    passed_order = order_a[passed]
    for j in range(i - 1, -1, -1):
        if ticks[i] - ticks[j] > transition_s:
            break
        if holder_arr[j, jp] == passed and holder_arr[j, jp1] == passer:
            contested = {position, position + 1}
            for k in range(j + 1, i):
                pair = (passer_order[k], passed_order[k])
                finite = [int(order) for order in pair if np.isfinite(order)]
                if any(order not in contested for order in finite):
                    break
                if len(finite) == 2 and passer_order[k] < passed_order[k]:
                    break
            else:
                return j
    return None


def _confidence_and_evidence(
    *,
    distance: float,
    proximity_limit: float,
    gap_s: float,
    battle_gap_s: float,
    transition_s: float,
    consecutive: bool,
) -> tuple[float, str, str]:
    """Score and explain the evidence behind an accepted pass."""
    proximity_margin = (
        1.0 if np.isinf(proximity_limit) else 1.0 - min(distance / proximity_limit, 1.0)
    )
    gap_margin = 1.0 - min(max(gap_s, 0.0) / battle_gap_s, 1.0)
    temporal_clarity = 1.0 if consecutive else 0.75
    confidence = float(
        np.clip(
            0.5 + 0.2 * proximity_margin + 0.2 * gap_margin + 0.1 * temporal_clarity,
            0,
            1,
        )
    )
    reason = "clean_adjacent_swap" if consecutive else "adjacent_swap_after_short_transition"
    evidence = (
        f"transition_s={transition_s:.2f};distance={distance:.2f};"
        f"proximity_limit={proximity_limit:.2f};gap_s={gap_s:.2f};"
        f"gap_limit_s={battle_gap_s:.2f};persistence=confirmed"
    )
    return round(confidence, 3), evidence, reason


def detect_overtakes(
    replay: pd.DataFrame,
    battle_gap_s: float = _BATTLE_GAP_S,
    persist_s: float = _PERSIST_S,
    start_guard_s: float = _START_GUARD_S,
    proximity_frac: float = _PROXIMITY_FRAC,
    transition_s: float = _TRANSITION_S,
) -> pd.DataFrame:
    """Detect on-track overtakes from one race's replay frame.

    ``replay`` needs ``driver_code``, ``t_s``, ``running_order``,
    ``gap_to_ahead_s``, ``x`` and ``y`` (one row per car per tick, as materialised
    in ``marts.race_replay``). Returns one row per confirmed pass — ``t_s`` (when
    the pass completes), ``for_position`` (the position the passer gains),
    ``passer_code``, ``passed_code`` and ``gap_at_pass_s`` (their interval just
    after the swap). ``confidence``, ``evidence`` and ``reason`` make the accepted
    detector evidence explicit. Results are sorted by ``t_s``.

    A pass is counted when the holder of a position changes from B to A and the
    pair can be traced back to the opposite adjacent order within ``transition_s``.
    An intermediate tick may omit one of the pair, but neither car may occupy a
    finite position outside the two contested places. The cars must also be close
    at completion (the pit-cycle discriminator), have an interval under
    ``battle_gap_s`` and remain swapped for ``persist_s``. Ticks before
    ``start_guard_s`` are skipped.
    """
    required = {"driver_code", "t_s", "running_order", "gap_to_ahead_s", "x", "y"}
    missing = required - set(replay.columns)
    if missing:
        raise ValueError(f"replay is missing columns: {sorted(missing)}")

    df = replay.dropna(subset=["running_order", "t_s"]).copy()
    if df.empty:
        return _empty_overtakes()
    df = df.drop_duplicates(subset=["t_s", "driver_code"])
    df["running_order"] = df["running_order"].astype(int)

    # Physical-proximity threshold in position units, relative to the circuit extent.
    diag = float(np.hypot(df["x"].max() - df["x"].min(), df["y"].max() - df["y"].min()))
    prox_units = proximity_frac * diag if diag > 0 else np.inf

    # position -> holder code, per tick (rows = sorted ticks, cols = 1..N).
    holder = df.pivot(index="t_s", columns="running_order", values="driver_code").sort_index()
    ticks = holder.index.to_numpy(dtype=float)
    n_ticks = len(ticks)
    if n_ticks < 2:
        return _empty_overtakes()
    positions = [int(p) for p in holder.columns]
    pos_idx = {p: j for j, p in enumerate(positions)}
    holder_arr = holder.to_numpy(dtype=object)

    # Per-driver arrays over the same tick grid, for proximity and persistence.
    def _by_code(value: str) -> dict[str, np.ndarray]:
        wide = df.pivot(index="t_s", columns="driver_code", values=value).reindex(holder.index)
        return {str(c): wide[c].to_numpy(dtype=float) for c in wide.columns}

    order_a = _by_code("running_order")
    gap_a = _by_code("gap_to_ahead_s")
    x_a = _by_code("x")
    y_a = _by_code("y")

    rows: list[tuple[float, int, str, str, float, float, str, str]] = []
    for p in positions:
        if (p + 1) not in pos_idx:
            continue  # no car directly behind the last position
        jp = pos_idx[p]
        jp1 = pos_idx[p + 1]
        for i in range(1, n_ticks):
            t_now = float(ticks[i])
            if t_now < start_guard_s:
                continue
            passer = holder_arr[i, jp]
            passed = holder_arr[i, jp1]
            if not isinstance(passer, str) or not isinstance(passed, str) or passer == passed:
                continue
            # Only evaluate the completion tick, then find the nearby pre-swap
            # adjacent order through at most one short incomplete transition.
            if holder_arr[i - 1, jp] == passer:
                continue
            anchor = _transition_anchor(
                holder_arr,
                order_a,
                ticks,
                i,
                jp,
                jp1,
                p,
                passer,
                passed,
                transition_s,
            )
            if anchor is None:
                continue
            # Physical proximity at the completion tick — the pit-cycle discriminator.
            dx = x_a[passer][i] - x_a[passed][i]
            dy = y_a[passer][i] - y_a[passed][i]
            distance = float(np.hypot(dx, dy))
            if not distance < prox_units:
                continue
            gap_now = gap_a[passed][i]  # the passed car's new interval to the passer
            if not gap_now < battle_gap_s:
                continue
            if not _stays_ahead(order_a, passer, passed, ticks, i, persist_s):
                continue
            transition_duration = float(ticks[i] - ticks[anchor])
            confidence, evidence, reason = _confidence_and_evidence(
                distance=distance,
                proximity_limit=prox_units,
                gap_s=float(gap_now),
                battle_gap_s=battle_gap_s,
                transition_s=transition_duration,
                consecutive=anchor == i - 1,
            )
            rows.append(
                (
                    t_now,
                    int(p),
                    passer,
                    passed,
                    round(float(gap_now), 2),
                    confidence,
                    evidence,
                    reason,
                )
            )

    if not rows:
        return _empty_overtakes()
    out = pd.DataFrame(rows, columns=_COLUMNS).sort_values("t_s").reset_index(drop=True)
    log.info("overtakes.detected", passes=len(out))
    return out


def _empty_overtakes() -> pd.DataFrame:
    # Preserve SQL types when a newly processed race has no passes. Otherwise
    # DuckDB infers empty object columns as integers and rejects later drivers.
    strings = {"passer_code", "passed_code", "evidence", "reason"}
    return pd.DataFrame(
        {
            column: pd.Series(
                dtype="string"
                if column in strings
                else "Int64"
                if column == "for_position"
                else "float64"
            )
            for column in _COLUMNS
        }
    )
