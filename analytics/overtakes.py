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

_COLUMNS = ["t_s", "for_position", "passer_code", "passed_code", "gap_at_pass_s"]


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


def detect_overtakes(
    replay: pd.DataFrame,
    battle_gap_s: float = _BATTLE_GAP_S,
    persist_s: float = _PERSIST_S,
    start_guard_s: float = _START_GUARD_S,
    proximity_frac: float = _PROXIMITY_FRAC,
) -> pd.DataFrame:
    """Detect on-track overtakes from one race's replay frame.

    ``replay`` needs ``driver_code``, ``t_s``, ``running_order``,
    ``gap_to_ahead_s``, ``x`` and ``y`` (one row per car per tick, as materialised
    in ``marts.race_replay``). Returns one row per confirmed pass — ``t_s`` (when
    the pass completes), ``for_position`` (the position the passer gains),
    ``passer_code``, ``passed_code`` and ``gap_at_pass_s`` (their interval just
    after the swap) — sorted by ``t_s``.

    A pass is counted when, between two consecutive ticks, the holder of a position
    changes from B to A **and** A was directly behind B on the previous tick (a
    clean single-place swap) **and** the two cars are physically close at the
    completion tick (``proximity_frac`` of the track extent — this is what excludes
    pit-cycle swaps) **and** their interval is under ``battle_gap_s`` **and** A
    stays ahead of B for ``persist_s`` afterwards. Ticks before ``start_guard_s``
    are skipped.
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

    rows: list[tuple[float, int, str, str, float]] = []
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
            passed = holder_arr[i - 1, jp]
            if not isinstance(passer, str) or not isinstance(passed, str) or passer == passed:
                continue
            # The passer must have been directly behind (at p+1) the tick before,
            # and the passed car must now sit directly behind it — a clean swap.
            if holder_arr[i - 1, jp1] != passer or holder_arr[i, jp1] != passed:
                continue
            # Physical proximity at the completion tick — the pit-cycle discriminator.
            dx = x_a[passer][i] - x_a[passed][i]
            dy = y_a[passer][i] - y_a[passed][i]
            if not np.hypot(dx, dy) < prox_units:
                continue
            gap_now = gap_a[passed][i]  # the passed car's new interval to the passer
            if not gap_now < battle_gap_s:
                continue
            if not _stays_ahead(order_a, passer, passed, ticks, i, persist_s):
                continue
            rows.append((t_now, int(p), passer, passed, round(float(gap_now), 2)))

    if not rows:
        return _empty_overtakes()
    out = pd.DataFrame(rows, columns=_COLUMNS).sort_values("t_s").reset_index(drop=True)
    log.info("overtakes.detected", passes=len(out))
    return out


def _empty_overtakes() -> pd.DataFrame:
    return pd.DataFrame(columns=_COLUMNS)
