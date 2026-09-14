"""Experimental pair order and interval audit, never a production pressure input.

Positions are sparse change events. Intervals are separate observations without
an opponent identifier. Only an adjacent, unambiguous pair can supply that
identity, and every topology change invalidates earlier interval observations.
Held observations expose their age; they are not extra measured samples.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from typing import Any

MAX_INTERVAL_AGE_S = 4.0


def _timestamp(value: str) -> float:
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        raise ValueError("Source timestamp requires timezone")
    return stamp.timestamp()


def pair_samples(
    positions: dict[int, list[dict[str, Any]]],
    intervals: dict[int, list[dict[str, Any]]],
    ticks: list[float],
) -> list[dict[str, Any]]:
    """Sample source states with no future lookup or fallback to model gaps.

    The four-second age cap is an experimental policy, not a completeness
    guarantee. A sparse position feed has no heartbeat, so order coverage cannot
    be certified by this adapter. Callers must not mix this pair into full-field
    replay ranks or use held samples as continuous pressure evidence.
    """
    if len(positions) != 2 or set(positions) != set(intervals):
        raise ValueError("Matching streams for two drivers are required")
    return _samples(positions, intervals, ticks, complete_field=False)


def field_samples(
    positions: dict[int, list[dict[str, Any]]],
    intervals: dict[int, list[dict[str, Any]]],
    ticks: list[float],
) -> list[dict[str, Any]]:
    """Audit a declared full roster without mixing pair ranks into a model field.

    Every driver must have a unique position in 1..N at the sampled instant.
    Unknown, duplicate or skipped ranks invalidate the whole field. This checks
    internal coherence, not feed completeness: callers must supply the actual
    race roster, including retirees, and sparse feeds have no heartbeat.
    """
    if len(positions) < 2 or set(positions) != set(intervals):
        raise ValueError("Matching position and interval streams for the roster are required")
    return _samples(positions, intervals, ticks, complete_field=True)


def _samples(
    positions: dict[int, list[dict[str, Any]]],
    intervals: dict[int, list[dict[str, Any]]],
    ticks: list[float],
    *,
    complete_field: bool,
) -> list[dict[str, Any]]:
    if any(not math.isfinite(t) for t in ticks) or ticks != sorted(set(ticks)):
        raise ValueError("Ticks must be finite, unique and increasing")
    updates: dict[float, dict[tuple[str, int], Any]] = defaultdict(dict)
    for kind, streams in (("position", positions), ("interval", intervals)):
        for driver, rows in streams.items():
            for row in rows:
                if row["driver_number"] != driver:
                    raise ValueError("Source driver mismatch")
                when = _timestamp(row["date"])
                value = row.get("position") if kind == "position" else row.get("interval")
                key = (kind, driver)
                if key in updates[when] and updates[when][key] != value:
                    raise ValueError("Conflicting simultaneous source observations")
                updates[when][key] = value
    ranks: dict[int, int | None] = dict.fromkeys(positions)
    gaps: dict[int, tuple[float, Any]] = {}
    epoch = -math.inf
    ordered = iter(sorted(updates.items()))
    pending = next(ordered, None)
    result = []
    for tick in ticks:
        while pending is not None and pending[0] <= tick:
            when, batch = pending
            previous = ranks.copy()
            for (kind, driver), value in batch.items():
                if kind == "position":
                    ranks[driver] = value if type(value) is int and value > 0 else None
                else:
                    gaps[driver] = (when, value)
            if ranks != previous:
                epoch = when
            pending = next(ordered, None)
        valid = None not in ranks.values() and len(set(ranks.values())) == len(ranks)
        if complete_field:
            valid = valid and set(ranks.values()) == set(range(1, len(ranks) + 1))
        by_rank = {rank: driver for driver, rank in ranks.items()} if valid else {}
        for driver, rank in ranks.items():
            opponent = by_rank.get(rank - 1) if rank is not None else None
            when, value = gaps.get(driver, (-math.inf, None))
            age = tick - when
            reason = "available"
            if not valid:
                reason = "unknown_order"
            elif opponent is None:
                reason = "no_observed_pair_ahead"
            elif when < epoch:
                reason = "interval_predates_order_change"
            elif age > MAX_INTERVAL_AGE_S:
                reason = "stale_interval"
            elif type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                reason = "non_numeric_interval"
            result.append(
                {
                    "utc_s": tick,
                    "driver_number": driver,
                    "running_order": rank if valid else None,
                    "ahead_driver_number": opponent,
                    "gap_to_ahead_s": float(value) if reason == "available" else None,
                    "interval_observed_utc_s": when if math.isfinite(when) else None,
                    "interval_age_s": age if math.isfinite(age) else None,
                    "gap_status": reason,
                    "pressure_eligible": False,
                }
            )
    return result
