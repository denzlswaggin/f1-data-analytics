"""Race replay: resample every car onto one shared clock for an animated map.

FastF1's positional feed gives each car's X/Y stamped with ``session_time_sec``,
but sampled at slightly different instants per car and over the whole session
(garage → in-laps included). To animate all cars *moving together* we:

1. clip to the race window (first lap start → last lap end, from lap timing);
2. interpolate every car's X/Y onto a single uniform time grid (``tick_s``);
3. reconstruct each car's **lap progress** curve (fractional laps completed) from
   the lap-start/lap-time table, so we can rank the field and measure time gaps at
   any instant.

The output is a compact long frame — one row per car per tick — that the browser
interpolates between for smooth motion. All logic is pure (no warehouse, no
FastF1) so it unit-tests on synthetic frames.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from ingestion.logging import get_logger

log = get_logger(__name__)

# A retired car's positional feed keeps reporting its parked spot to the end of the
# session; cap its on-track window this long after its last lap so it vanishes
# instead of leaving a dead dot (the buffer shows the slow-down / return to pits).
_RETIRE_BUFFER_S = 30.0
# Movement (in position units) below which a car is treated as stationary/parked —
# used only to retire cars that never completed a lap.
_MOVE_EPS_UNITS = 10.0


def _progress_curve(grid: np.ndarray, laps_d: pd.DataFrame) -> np.ndarray:
    """Fractional laps completed by each grid time for one driver.

    Built from lap breakpoints: at ``lap_start_sec`` of lap L the driver has
    completed ``L-1`` laps; at ``lap_start_sec + lap_time_sec`` they've completed
    ``L``. Linear between breakpoints. NaN before the first lap starts; clamped
    (frozen) after the last recorded lap, so finishers stay ranked while retirees
    are dropped by the position-based active mask instead.
    """
    if laps_d.empty:
        return np.full(grid.shape, np.nan)
    start = laps_d["lap_start_sec"].to_numpy(dtype="float64")
    dur = laps_d["lap_time_sec"].to_numpy(dtype="float64")
    lapno = laps_d["lap_number"].to_numpy(dtype="float64")

    xp = [float(start[0])]
    fp = [float(lapno[0] - 1.0)]
    for s, d, lap in zip(start, dur, lapno, strict=True):
        end = s + d if np.isfinite(d) else s
        if end > xp[-1]:  # keep the breakpoint sequence strictly increasing
            xp.append(float(end))
            fp.append(float(lap))
    if len(xp) < 2:
        return np.full(grid.shape, np.nan)

    prog: np.ndarray = np.interp(grid, np.asarray(xp), np.asarray(fp))
    prog[grid < xp[0]] = np.nan
    return prog


def resample_race(positions: pd.DataFrame, laps: pd.DataFrame, tick_s: float = 1.0) -> pd.DataFrame:
    """Resample a race onto a shared time grid with running order and gaps.

    ``positions`` needs ``driver_code``, ``session_time_sec``, ``x``, ``y``.
    ``laps`` needs ``driver_code``, ``lap_number``, ``lap_start_sec``,
    ``lap_time_sec``. Returns one row per driver per tick with ``t_s`` (seconds
    since race start), ``x``, ``y``, ``running_order``, ``gap_to_leader_s`` and
    ``gap_to_ahead_s`` — restricted to ticks where the car has position data.
    """
    required_pos = {"driver_code", "session_time_sec", "x", "y"}
    required_lap = {"driver_code", "lap_number", "lap_start_sec", "lap_time_sec"}
    for name, df, req in [("positions", positions, required_pos), ("laps", laps, required_lap)]:
        missing = req - set(df.columns)
        if missing:
            raise ValueError(f"{name} is missing columns: {sorted(missing)}")

    # Defensive clean: drop any (0,0) sentinels that slipped through (raw is cleaned
    # at ingest, but keep the pure function robust on dirty input).
    positions = positions[~((positions["x"] == 0) & (positions["y"] == 0))]
    laps = laps.dropna(subset=["lap_start_sec"])
    if positions.empty or laps.empty:
        return _empty_replay()

    # Race window: green light (first lap start) to the last lap crossing.
    t0 = float(laps["lap_start_sec"].min())
    t1 = float((laps["lap_start_sec"] + laps["lap_time_sec"].fillna(0.0)).max())
    if not np.isfinite(t0) or not np.isfinite(t1) or t1 <= t0:
        return _empty_replay()
    grid = np.arange(t0, t1 + tick_s, tick_s)
    n_ticks = len(grid)

    drivers = sorted(positions["driver_code"].dropna().unique())
    n = len(drivers)
    X = np.full((n, n_ticks), np.nan)
    Y = np.full((n, n_ticks), np.nan)
    P = np.full((n, n_ticks), np.nan)
    active = np.zeros((n, n_ticks), dtype=bool)
    # Session time each car crosses the line for the last time (finish/retirement).
    t_finish = np.full(n, np.inf)

    for i, d in enumerate(drivers):
        p = positions[positions["driver_code"] == d].sort_values("session_time_sec")
        pt = p["session_time_sec"].to_numpy(dtype="float64")
        if len(pt) < 2:
            continue
        px = p["x"].to_numpy(dtype="float64")
        py = p["y"].to_numpy(dtype="float64")
        X[i] = np.interp(grid, pt, px)
        Y[i] = np.interp(grid, pt, py)
        dl = laps[laps["driver_code"] == d].sort_values("lap_number")
        P[i] = _progress_curve(grid, dl)
        if not dl.empty:
            last = dl.iloc[-1]
            dur = last["lap_time_sec"]
            t_finish[i] = float(last["lap_start_sec"]) + (float(dur) if np.isfinite(dur) else 0.0)
            cap = t_finish[i] + _RETIRE_BUFFER_S
        else:
            # No lap data (e.g. a lap-1 crash): fall back to the last time the car
            # actually moved, so a parked car doesn't linger on the map either.
            moved = np.where(np.hypot(np.diff(px), np.diff(py)) > _MOVE_EPS_UNITS)[0]
            cap = float(pt[moved[-1] + 1] if moved.size else pt[0]) + _RETIRE_BUFFER_S
        # On track within its own sampled window, but not past retirement — a retired
        # car's feed keeps reporting its parked spot to the end, so vanish it there.
        active[i] = (grid >= pt.min()) & (grid <= min(float(pt.max()), cap))

    # Leader progress = leading edge across the field; monotonic by construction.
    leader_prog = np.nanmax(np.where(active, P, np.nan), axis=0)
    leader_prog = np.where(np.isfinite(leader_prog), leader_prog, 0.0)
    leader_prog = np.maximum.accumulate(leader_prog)
    # Invert with the FIRST time each progress level was reached; the leader curve
    # plateaus at the winner's lap count to the end of the grid, and a plain interp
    # against that plateau would map every lead-lap finisher to t1 (gap 0).
    uniq_prog, first_idx = np.unique(leader_prog, return_index=True)
    leader_reach_time = grid[first_idx]

    # Gap to leader = now minus when the leader reached this car's progress. This is
    # correct while the car is racing, but its lap-progress plateaus at the finish
    # (so the inverse then drifts) — hold the gap at its finishing value afterwards.
    G = np.full((n, n_ticks), np.nan)
    for i in range(n):
        finite = np.isfinite(P[i])
        if not finite.any():
            continue
        leader_time = np.interp(P[i][finite], uniq_prog, leader_reach_time)
        G[i, finite] = np.clip(grid[finite] - leader_time, 0.0, None)
        if np.isfinite(t_finish[i]):
            fin_idx = min(int(np.searchsorted(grid, t_finish[i], side="left")), n_ticks - 1)
            G[i, fin_idx:] = G[i, fin_idx]

    order = np.full((n, n_ticks), np.nan)
    ahead = np.full((n, n_ticks), np.nan)
    rank_ok = active & np.isfinite(P)
    for t in range(n_ticks):
        act = np.where(rank_ok[:, t])[0]
        if act.size == 0:
            continue
        # Order by lap progress (desc); break ties (lead-lap finishers all plateau
        # at the same progress) by who crossed the line first — the finishing order.
        srt = act[np.lexsort((t_finish[act], -P[act, t]))]
        order[srt, t] = np.arange(1, srt.size + 1)
        gl = G[srt, t]
        ah = np.empty_like(gl)
        ah[0] = 0.0
        ah[1:] = np.clip(np.diff(gl), 0.0, None)
        ahead[srt, t] = ah

    frames: list[pd.DataFrame] = []
    for i, d in enumerate(drivers):
        mask = active[i]
        if not mask.any():
            continue
        frames.append(
            pd.DataFrame(
                {
                    "driver_code": d,
                    "t_s": np.round(grid[mask] - t0, 2),
                    "x": np.rint(X[i, mask]),
                    "y": np.rint(Y[i, mask]),
                    "running_order": order[i, mask],
                    "gap_to_leader_s": np.round(G[i, mask], 2),
                    "gap_to_ahead_s": np.round(ahead[i, mask], 2),
                }
            )
        )

    out = pd.concat(frames, ignore_index=True) if frames else _empty_replay()
    out["running_order"] = out["running_order"].astype("Int64")
    log.info("replay.resampled", drivers=n, ticks=n_ticks, rows=len(out), tick_s=tick_s)
    return out


def _empty_replay() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "driver_code",
            "t_s",
            "x",
            "y",
            "running_order",
            "gap_to_leader_s",
            "gap_to_ahead_s",
        ]
    )
