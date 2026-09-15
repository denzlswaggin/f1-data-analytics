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

# Movement (in position units, ~1/10 m) below which two consecutive samples count
# as "not moving". A parked car's feed repeats its exact coordinate (step 0), so a
# small epsilon cleanly separates stopped from moving without over-clipping crawls.
_MOVE_EPS_UNITS = 0.5
# Default grace (s) to keep showing a car after it stops before it vanishes; the
# pipeline overrides this from settings (F1_REPLAY_RETIRE_BUFFER_S).
_RETIRE_BUFFER_S = 5.0
# Default safety cap (s): a retiree is never shown more than this long past its last
# completed lap, guarding against a recovered car whose position keeps moving.
_RETIRE_MAX_LINGER_S = 120.0
# Refuse to publish a replay when the position feed covers only a fragment of
# the lap-timing race window. A small tail is tolerated because the two FastF1
# feeds do not always stop on exactly the same timestamp.
_MIN_POSITION_COVERAGE = 0.90
# Maximum separation between genuine coordinate updates that may be interpolated.
# FastF1 normally updates several times per second, but some feeds hold one coordinate
# for a few seconds. Wider gaps are outages (or garage/recovery moves), not a route the
# replay should invent as a straight line.
_MAX_POSITION_GAP_S = 10.0
_MAX_RECORDED_INTERVAL_AGE_S = 4.0


class IncompleteReplayError(ValueError):
    """Raised when a position feed covers too little of its race window."""


def _position_interpolation_points(
    samples: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return finite, strictly timed X/Y points with sample-and-hold runs collapsed.

    Some FastF1 position feeds repeat a coordinate for several packets and then jump
    to the next measured point. Treating every repeated packet as a real stationary
    observation creates stop-and-sprint motion. A coordinate run instead represents
    one quantised observation over a time interval, so anchor it at that interval's
    midpoint and interpolate between the genuine updates.

    The caller keeps the uncollapsed samples for retirement detection: a car that is
    actually parked still needs to disappear after the configured grace period.
    """
    finite = samples[["session_time_sec", "x", "y"]].apply(pd.to_numeric, errors="coerce")
    finite = finite[np.isfinite(finite).all(axis=1)]
    finite = finite[~((finite["x"] == 0) & (finite["y"] == 0))]
    finite = (
        finite.sort_values("session_time_sec")
        .drop_duplicates(subset=["session_time_sec"], keep="last")
        .reset_index(drop=True)
    )
    if finite.empty:
        empty = np.asarray([], dtype="float64")
        return empty, empty, empty

    pt = finite["session_time_sec"].to_numpy(dtype="float64")
    px = finite["x"].to_numpy(dtype="float64")
    py = finite["y"].to_numpy(dtype="float64")
    changed = np.concatenate(([True], np.hypot(np.diff(px), np.diff(py)) > _MOVE_EPS_UNITS))
    starts = np.flatnonzero(changed)
    ends = np.concatenate((starts[1:] - 1, [len(pt) - 1]))
    midpoint_t = (pt[starts] + pt[ends]) / 2.0
    # The final coordinate has no later update with which to bound a quantisation
    # interval. Anchor it when it first arrived; otherwise a genuinely parked car's
    # long final run would move its stopping point far into the future.
    midpoint_t[-1] = pt[starts[-1]]
    return midpoint_t, px[starts], py[starts]


def _interpolation_support(grid: np.ndarray, sample_t: np.ndarray, max_gap_s: float) -> np.ndarray:
    """Mark grid points that do not require bridging a source-position outage."""
    if sample_t.size < 2:
        return np.ones(grid.shape, dtype=bool)
    right = np.searchsorted(sample_t, grid, side="right")
    between = (right > 0) & (right < sample_t.size)
    supported = ~between
    supported[between] = sample_t[right[between]] - sample_t[right[between] - 1] <= max_gap_s
    left = right - 1
    exact = (left >= 0) & np.isclose(grid, sample_t[np.clip(left, 0, sample_t.size - 1)])
    supported[exact] = True
    return supported


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
        # An unfinished/red-flagged lap commonly has a start timestamp but no
        # duration. Crediting that lap at its start moves the driver one whole lap
        # ahead and can manufacture a false leader. Only a measured positive
        # duration may advance completed progress.
        if not np.isfinite(d) or d <= 0:
            continue
        end = s + d
        if end > xp[-1]:  # keep the breakpoint sequence strictly increasing
            xp.append(float(end))
            fp.append(float(lap))
    if len(xp) < 2:
        return np.full(grid.shape, np.nan)

    prog: np.ndarray = np.interp(grid, np.asarray(xp), np.asarray(fp))
    prog[grid < xp[0]] = np.nan
    return prog


def _lap_state_curves(
    grid: np.ndarray, laps_d: pd.DataFrame
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return the current lap and tyre state for each point on ``grid``.

    Lap attributes are step values: a new lap, stint, compound and tyre age take
    effect at that lap's ``lap_start_sec``. ``lap_progress`` is the continuous
    0..1 fraction through the current lap. It freezes at 1 after the driver's
    final recorded lap, matching the existing progress/ranking behaviour.

    Tyre columns are optional for backwards-compatible use of ``resample_race``
    with the original four-column lap contract. Missing attributes remain null.
    """
    shape = grid.shape
    lap_number = np.full(shape, np.nan)
    lap_progress = np.full(shape, np.nan)
    stint = np.full(shape, np.nan)
    compound = np.full(shape, None, dtype=object)
    tyre_life = np.full(shape, np.nan)
    if laps_d.empty:
        return lap_number, lap_progress, stint, compound, tyre_life

    ordered = (
        laps_d.dropna(subset=["lap_start_sec", "lap_number"])
        .sort_values(["lap_start_sec", "lap_number"])
        .drop_duplicates(subset=["lap_start_sec"], keep="last")
    )
    if ordered.empty:
        return lap_number, lap_progress, stint, compound, tyre_life

    starts = ordered["lap_start_sec"].to_numpy(dtype="float64")
    durations = pd.to_numeric(ordered["lap_time_sec"], errors="coerce").to_numpy(dtype="float64")
    indices = np.searchsorted(starts, grid, side="right") - 1
    valid = indices >= 0
    selected = indices[valid]

    lap_values = pd.to_numeric(ordered["lap_number"], errors="coerce").to_numpy(dtype="float64")
    lap_number[valid] = lap_values[selected]

    selected_durations = durations[selected]
    timed = valid.copy()
    timed[valid] = np.isfinite(selected_durations) & (selected_durations > 0)
    timed_indices = indices[timed]
    lap_progress[timed] = np.clip(
        (grid[timed] - starts[timed_indices]) / durations[timed_indices],
        0.0,
        1.0,
    )

    if "stint" in ordered:
        stint_values = pd.to_numeric(ordered["stint"], errors="coerce").to_numpy(dtype="float64")
        stint[valid] = stint_values[selected]
    if "compound" in ordered:
        compound_values = ordered["compound"].astype("string").to_numpy(dtype=object)
        compound[valid] = compound_values[selected]
    if "tyre_life" in ordered:
        tyre_values = pd.to_numeric(ordered["tyre_life"], errors="coerce").to_numpy(dtype="float64")
        tyre_life[valid] = tyre_values[selected]

    return lap_number, lap_progress, stint, compound, tyre_life


def replay_source_coverage(positions: pd.DataFrame, laps: pd.DataFrame) -> float | None:
    """Return position-feed coverage of the race window as a 0..1 ratio.

    The median first/last position timestamp is used so one driver with a stray
    late packet cannot make a truncated feed look complete. ``None`` means the
    inputs are empty or do not contain a usable race window.
    """
    if positions.empty or laps.empty:
        return None

    lap_start = pd.to_numeric(laps["lap_start_sec"], errors="coerce")
    lap_end = lap_start + pd.to_numeric(laps["lap_time_sec"], errors="coerce")
    race_start = float(lap_start.min())
    race_end = float(lap_end.max())
    if not np.isfinite(race_start) or not np.isfinite(race_end) or race_end <= race_start:
        return None

    driver_windows = positions.groupby("driver_code")["session_time_sec"].agg(["min", "max"])
    if driver_windows.empty:
        return None
    position_start = float(driver_windows["min"].median())
    position_end = float(driver_windows["max"].median())
    if not np.isfinite(position_start) or not np.isfinite(position_end):
        return None

    covered_start = max(race_start, position_start)
    covered_end = min(race_end, position_end)
    covered = max(0.0, covered_end - covered_start)
    return min(1.0, covered / (race_end - race_start))


def validate_replay_sources(
    positions: pd.DataFrame,
    laps: pd.DataFrame,
    *,
    minimum_coverage: float = _MIN_POSITION_COVERAGE,
) -> None:
    """Raise when non-empty position data cannot support a full-race replay."""
    coverage = replay_source_coverage(positions, laps)
    if coverage is not None and coverage < minimum_coverage:
        raise IncompleteReplayError(
            "position feed covers only "
            f"{coverage:.1%} of the lap-timing race window; expected at least "
            f"{minimum_coverage:.0%}"
        )


def _overlay_recorded_timing(
    grid: np.ndarray,
    drivers: list[str],
    active: np.ndarray,
    order: np.ndarray,
    ahead: np.ndarray,
    leader_gap: np.ndarray,
    order_source: np.ndarray,
    order_confidence: np.ndarray,
    order_observed_t: np.ndarray,
    gap_source: np.ndarray,
    gap_confidence: np.ndarray,
    gap_observed_t: np.ndarray,
    source_order: pd.DataFrame | None,
    source_intervals: pd.DataFrame | None,
) -> None:
    """Overlay coherent recorded order and fresh gaps onto model arrays in place."""
    if source_order is None or source_order.empty:
        return
    required = {"driver_code", "session_time_sec", "position"}
    missing = required - set(source_order.columns)
    if missing:
        raise ValueError(f"source_order is missing columns: {sorted(missing)}")

    recorded = source_order.copy()
    recorded["driver_code"] = recorded["driver_code"].astype("string")
    for column in ("session_time_sec", "position"):
        recorded[column] = pd.to_numeric(recorded[column], errors="coerce")
    recorded = recorded.loc[
        recorded["driver_code"].isin(drivers)
        & np.isfinite(recorded["session_time_sec"])
        & recorded["position"].gt(0)
        & recorded["position"].mod(1).eq(0)
    ].sort_values(["session_time_sec", "driver_code"])
    if recorded.empty:
        return

    interval_rows = pd.DataFrame()
    if source_intervals is not None and not source_intervals.empty:
        interval_required = {
            "driver_code",
            "session_time_sec",
            "gap_to_leader_s",
            "gap_to_ahead_s",
        }
        missing = interval_required - set(source_intervals.columns)
        if missing:
            raise ValueError(f"source_intervals is missing columns: {sorted(missing)}")
        interval_rows = source_intervals.copy()
        interval_rows["driver_code"] = interval_rows["driver_code"].astype("string")
        for column in ("session_time_sec", "gap_to_leader_s", "gap_to_ahead_s"):
            interval_rows[column] = pd.to_numeric(interval_rows[column], errors="coerce")
        interval_rows = interval_rows.loc[
            interval_rows["driver_code"].isin(drivers)
            & np.isfinite(interval_rows["session_time_sec"])
        ].sort_values(["session_time_sec", "driver_code"])

    order_records = recorded.to_dict("records")
    gap_records = interval_rows.to_dict("records")
    order_cursor = 0
    gap_cursor = 0
    positions: dict[str, int] = {}
    position_times: dict[str, float] = {}
    gaps: dict[str, tuple[float, float, float]] = {}
    topology_epoch = -np.inf
    roster_ranks = set(range(1, len(drivers) + 1))

    for tick_index, when in enumerate(grid):
        while order_cursor < len(order_records) and float(
            order_records[order_cursor]["session_time_sec"]
        ) <= when:
            batch_time = float(order_records[order_cursor]["session_time_sec"])
            changed = False
            while order_cursor < len(order_records) and np.isclose(
                float(order_records[order_cursor]["session_time_sec"]), batch_time
            ):
                row = order_records[order_cursor]
                driver = str(row["driver_code"])
                value = int(row["position"])
                changed = changed or positions.get(driver) != value
                positions[driver] = value
                position_times[driver] = batch_time
                order_cursor += 1
            if changed:
                topology_epoch = batch_time

        while gap_cursor < len(gap_records) and float(
            gap_records[gap_cursor]["session_time_sec"]
        ) <= when:
            row = gap_records[gap_cursor]
            driver = str(row["driver_code"])
            gaps[driver] = (
                float(row["session_time_sec"]),
                float(row["gap_to_leader_s"]),
                float(row["gap_to_ahead_s"]),
            )
            gap_cursor += 1

        if set(positions) != set(drivers) or set(positions.values()) != roster_ranks:
            continue
        active_indices = np.where(active[:, tick_index])[0]
        if active_indices.size == 0:
            continue
        ranked = sorted(active_indices, key=lambda idx: positions[drivers[idx]])
        active_codes = {drivers[idx] for idx in active_indices}
        full_by_rank = {rank: driver for driver, rank in positions.items()}
        for dense_rank, driver_index in enumerate(ranked, start=1):
            driver = drivers[driver_index]
            full_rank = positions[driver]
            order[driver_index, tick_index] = dense_rank
            order_source[driver_index, tick_index] = "openf1_recorded"
            order_confidence[driver_index, tick_index] = "High"
            order_observed_t[driver_index, tick_index] = position_times[driver]

            if full_rank == 1:
                leader_gap[driver_index, tick_index] = 0.0
                ahead[driver_index, tick_index] = 0.0
                gap_source[driver_index, tick_index] = "openf1_recorded"
                gap_confidence[driver_index, tick_index] = "High"
                gap_observed_t[driver_index, tick_index] = position_times[driver]
                continue
            predecessor = full_by_rank.get(full_rank - 1)
            observation = gaps.get(driver)
            if predecessor not in active_codes or observation is None:
                continue
            observed_at, gap_leader, gap_ahead = observation
            if (
                observed_at < topology_epoch
                or when - observed_at > _MAX_RECORDED_INTERVAL_AGE_S
                or not np.isfinite(gap_leader)
                or not np.isfinite(gap_ahead)
                or gap_leader < 0
                or gap_ahead < 0
            ):
                continue
            leader_gap[driver_index, tick_index] = gap_leader
            ahead[driver_index, tick_index] = gap_ahead
            gap_source[driver_index, tick_index] = "openf1_recorded"
            gap_confidence[driver_index, tick_index] = "High"
            gap_observed_t[driver_index, tick_index] = observed_at


def resample_race(
    positions: pd.DataFrame,
    laps: pd.DataFrame,
    source_order: pd.DataFrame | None = None,
    source_intervals: pd.DataFrame | None = None,
    tick_s: float = 1.0,
    retire_buffer_s: float = _RETIRE_BUFFER_S,
    max_linger_s: float = _RETIRE_MAX_LINGER_S,
    max_position_gap_s: float = _MAX_POSITION_GAP_S,
) -> pd.DataFrame:
    """Resample a race onto a shared time grid with running order and gaps.

    ``positions`` needs ``driver_code``, ``session_time_sec``, ``x``, ``y``.
    ``laps`` needs ``driver_code``, ``lap_number``, ``lap_start_sec`` and
    ``lap_time_sec``; optional ``stint``, ``compound`` and ``tyre_life`` values
    enrich each tick. Returns one row per driver per tick with ``t_s`` (seconds
    since race start), ``x``, ``y``, ``running_order``, ``gap_to_leader_s`` and
    ``gap_to_ahead_s`` — restricted to ticks where the car is on track.

    A car is dropped once it **stops moving** (its position stops changing) plus
    ``retire_buffer_s`` grace, so retirees vanish where they pull off instead of
    freezing on the map. Using the *last* movement is red-flag-safe: a car that
    resumes has a later last-movement, so it isn't retired during the stoppage.
    ``source_order`` and ``source_intervals`` are optional timestamped state-change
    feeds on the same session clock. A complete coherent recorded order overrides
    the lap-progress estimate; a fresh interval overrides the modelled gap.

    ``max_linger_s`` caps this above: a retiree is never shown more than that long
    past its last completed lap (guards a recovered car whose sensor keeps moving).
    """
    required_pos = {"driver_code", "session_time_sec", "x", "y"}
    required_lap = {"driver_code", "lap_number", "lap_start_sec", "lap_time_sec"}
    for name, df, req in [("positions", positions, required_pos), ("laps", laps, required_lap)]:
        missing = req - set(df.columns)
        if missing:
            raise ValueError(f"{name} is missing columns: {sorted(missing)}")

    if max_position_gap_s <= 0:
        raise ValueError("max_position_gap_s must be greater than zero")

    # Defensive clean: raw ingestion already filters these, but replay snapshots can
    # be rebuilt from older or externally loaded position partitions.
    numeric = positions[["session_time_sec", "x", "y"]].apply(pd.to_numeric, errors="coerce")
    positions = positions[np.isfinite(numeric).all(axis=1)].copy()
    positions[["session_time_sec", "x", "y"]] = numeric[np.isfinite(numeric).all(axis=1)]
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
    lap_number = np.full((n, n_ticks), np.nan)
    lap_progress = np.full((n, n_ticks), np.nan)
    stint = np.full((n, n_ticks), np.nan)
    compound = np.full((n, n_ticks), None, dtype=object)
    tyre_life = np.full((n, n_ticks), np.nan)
    active = np.zeros((n, n_ticks), dtype=bool)
    # Session time each car crosses the line for the last time (finish/retirement).
    t_finish = np.full(n, np.inf)

    for i, d in enumerate(drivers):
        p = positions[positions["driver_code"] == d].sort_values("session_time_sec")
        raw_t = p["session_time_sec"].to_numpy(dtype="float64")
        raw_x = p["x"].to_numpy(dtype="float64")
        raw_y = p["y"].to_numpy(dtype="float64")
        if len(raw_t) < 2:
            continue
        pt, px, py = _position_interpolation_points(p)
        if not len(pt):
            continue
        X[i] = np.interp(grid, pt, px)
        Y[i] = np.interp(grid, pt, py)
        dl = laps[laps["driver_code"] == d].sort_values("lap_number")
        P[i] = _progress_curve(grid, dl)
        (
            lap_number[i],
            lap_progress[i],
            stint[i],
            compound[i],
            tyre_life[i],
        ) = _lap_state_curves(grid, dl)
        if not dl.empty:
            last = dl.iloc[-1]
            dur = last["lap_time_sec"]
            t_finish[i] = float(last["lap_start_sec"]) + (float(dur) if np.isfinite(dur) else 0.0)
        # Retire the car when it *last actually moves* (a parked feed repeats its spot),
        # plus the grace buffer. Finishers keep moving to the flag, so their run ends at
        # the grid bound (t1); retirees vanish where they stop, not frozen to the end.
        moved = np.where(np.hypot(np.diff(raw_x), np.diff(raw_y)) > _MOVE_EPS_UNITS)[0]
        stop_t = float(raw_t[moved[-1] + 1]) if moved.size else float(raw_t[0])
        cap = stop_t + retire_buffer_s
        # Safety cap: don't show a retiree more than max_linger_s past its last lap
        # (a recovered car's sensor can keep "moving" long after it's out).
        if np.isfinite(t_finish[i]):
            cap = min(cap, t_finish[i] + max_linger_s)
        support = _interpolation_support(grid, pt, max_position_gap_s)
        active[i] = (grid >= raw_t.min()) & (grid <= min(float(raw_t.max()), cap)) & support

    # Leader progress = leading edge across the field; monotonic by construction.
    active_progress = np.where(active, P, np.nan)
    has_progress = np.isfinite(active_progress).any(axis=0)
    leader_prog = np.zeros(n_ticks)
    leader_prog[has_progress] = np.nanmax(active_progress[:, has_progress], axis=0)
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
    order_source = np.full((n, n_ticks), None, dtype=object)
    order_confidence = np.full((n, n_ticks), None, dtype=object)
    order_observed_t = np.full((n, n_ticks), np.nan)
    gap_source = np.full((n, n_ticks), None, dtype=object)
    gap_confidence = np.full((n, n_ticks), None, dtype=object)
    gap_observed_t = np.full((n, n_ticks), np.nan)
    rank_ok = active & np.isfinite(P) & np.isfinite(lap_progress)
    for t in range(n_ticks):
        act = np.where(rank_ok[:, t])[0]
        active_at_tick = np.where(active[:, t])[0]
        # Partial ranks are worse than missing ranks: downstream code assumes one
        # dense, mutually consistent field. Missing current-lap progress therefore
        # withholds the entire model order at that tick.
        if act.size == 0 or not np.array_equal(act, active_at_tick):
            G[active_at_tick, t] = np.nan
            ahead[active_at_tick, t] = np.nan
            continue
        # Order by lap progress (desc); break ties (lead-lap finishers all plateau
        # at the same progress) by who crossed the line first — the finishing order.
        srt = act[np.lexsort((t_finish[act], -P[act, t]))]
        order[srt, t] = np.arange(1, srt.size + 1)
        order_source[srt, t] = "lap_progress_estimate"
        order_confidence[srt, t] = "Medium"
        gl = G[srt, t]
        ah = np.empty_like(gl)
        ah[0] = 0.0
        ah[1:] = np.clip(np.diff(gl), 0.0, None)
        ahead[srt, t] = ah
        gap_source[srt, t] = "lap_progress_estimate"
        gap_confidence[srt, t] = "Medium"

    _overlay_recorded_timing(
        grid,
        drivers,
        active,
        order,
        ahead,
        G,
        order_source,
        order_confidence,
        order_observed_t,
        gap_source,
        gap_confidence,
        gap_observed_t,
        source_order,
        source_intervals,
    )

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
                    "lap_number": lap_number[i, mask],
                    "lap_progress": np.round(lap_progress[i, mask], 4),
                    "stint": stint[i, mask],
                    "compound": compound[i, mask],
                    "tyre_life": tyre_life[i, mask],
                    "running_order": order[i, mask],
                    "gap_to_leader_s": np.round(G[i, mask], 2),
                    "gap_to_ahead_s": np.round(ahead[i, mask], 2),
                    "running_order_source": order_source[i, mask],
                    "running_order_confidence": order_confidence[i, mask],
                    "running_order_observed_t_s": np.round(order_observed_t[i, mask] - t0, 3),
                    "gap_source": gap_source[i, mask],
                    "gap_confidence": gap_confidence[i, mask],
                    "gap_observed_t_s": np.round(gap_observed_t[i, mask] - t0, 3),
                }
            )
        )

    out = pd.concat(frames, ignore_index=True) if frames else _empty_replay()
    for column in ["lap_number", "stint", "tyre_life", "running_order"]:
        out[column] = out[column].astype("Int64")
    out["compound"] = out["compound"].astype("string")
    for column in ["running_order_source", "running_order_confidence", "gap_source", "gap_confidence"]:
        out[column] = out[column].astype("string")
    log.info("replay.resampled", drivers=n, ticks=n_ticks, rows=len(out), tick_s=tick_s)
    return out


def _empty_replay() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "driver_code",
            "t_s",
            "x",
            "y",
            "lap_number",
            "lap_progress",
            "stint",
            "compound",
            "tyre_life",
            "running_order",
            "gap_to_leader_s",
            "gap_to_ahead_s",
            "running_order_source",
            "running_order_confidence",
            "running_order_observed_t_s",
            "gap_source",
            "gap_confidence",
            "gap_observed_t_s",
        ]
    )
