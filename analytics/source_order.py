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
        a, b = ranks
        ra, rb = ranks[a], ranks[b]
        valid = ra is not None and rb is not None and ra != rb
        adjacent = valid and abs(ra - rb) == 1  # type: ignore[operator]
        for driver, opponent in ((a, b), (b, a)):
            rank, other = ranks[driver], ranks[opponent]
            when, value = gaps.get(driver, (-math.inf, None))
            age = tick - when
            reason = "available"
            if not valid:
                reason = "unknown_order"
            elif not adjacent or rank < other:  # type: ignore[operator]
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
                    "ahead_driver_number": opponent if adjacent and rank > other else None,  # type: ignore[operator]
                    "gap_to_ahead_s": float(value) if reason == "available" else None,
                    "interval_observed_utc_s": when if math.isfinite(when) else None,
                    "interval_age_s": age if math.isfinite(age) else None,
                    "gap_status": reason,
                    "pressure_eligible": False,
                }
            )
    return result
