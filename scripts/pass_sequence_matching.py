"""Independent, ordered one-to-one matching of reference passes and detections."""

from __future__ import annotations

import math
from typing import Any


def _validate_event(event: dict[str, Any]) -> None:
    for field in ("passer_code", "passed_code"):
        value = event.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a nonempty driver code")
    if event["passer_code"] == event["passed_code"]:
        raise ValueError("passer_code and passed_code must differ")
    lap = event.get("lap_number")
    if isinstance(lap, bool) or not isinstance(lap, int) or lap < 1:
        raise ValueError("lap_number must be a positive integer")


def match_sequence(
    expected: list[dict[str, Any]],
    observed: list[dict[str, Any]],
    lap_tolerance: int = 0,
) -> dict[str, Any]:
    """Maximize matches without reordering references or reusing a detection.

    Observations are sorted by finite, unique ``t_s`` timestamps. Returned
    indices refer to the original input lists, not that sorted copy. Among
    maximum-cardinality assignments prefer the earliest observation, then
    earliest reference, at each match. Inputs are never mutated. This measures
    sequence agreement only; reference completeness is the caller's concern.
    """
    if isinstance(lap_tolerance, bool) or not isinstance(lap_tolerance, int) or lap_tolerance < 0:
        raise ValueError("lap_tolerance must be a nonnegative integer")
    for event in expected + observed:
        _validate_event(event)
    timestamps: set[float] = set()
    for event in observed:
        timestamp = event.get("t_s")
        if (
            isinstance(timestamp, bool)
            or not isinstance(timestamp, (int, float))
            or not math.isfinite(timestamp)
        ):
            raise ValueError("t_s must be a finite number")
        if timestamp in timestamps:
            raise ValueError("t_s timestamps must be unique for unambiguous order")
        timestamps.add(timestamp)
    chronological = sorted(enumerate(observed), key=lambda item: item[1]["t_s"])
    n, m = len(expected), len(observed)

    def compatible(i: int, j: int) -> bool:
        reference, detection = expected[i], chronological[j][1]
        return bool(
            reference["passer_code"] == detection["passer_code"]
            and reference["passed_code"] == detection["passed_code"]
            and abs(reference["lap_number"] - detection["lap_number"]) <= lap_tolerance
        )

    lengths = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            lengths[i][j] = max(lengths[i + 1][j], lengths[i][j + 1])
            if compatible(i, j):
                lengths[i][j] = max(lengths[i][j], 1 + lengths[i + 1][j + 1])

    matches: list[dict[str, int]] = []
    next_expected = 0
    remaining = lengths[0][0]
    for j in range(m):
        if not remaining:
            break
        for i in range(next_expected, n):
            if compatible(i, j) and 1 + lengths[i + 1][j + 1] == remaining:
                matches.append({"expected_index": i, "observed_index": chronological[j][0]})
                next_expected = i + 1
                remaining -= 1
                break
    matched_expected = {match["expected_index"] for match in matches}
    matched_observed = {match["observed_index"] for match in matches}
    return {
        "matches": matches,
        "unmatched_expected_indices": [i for i in range(n) if i not in matched_expected],
        "unmatched_observed_indices": [i for i in range(m) if i not in matched_observed],
    }
