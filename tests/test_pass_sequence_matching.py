"""Sequence matching tests independent of production event extraction."""

from __future__ import annotations

import runpy
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

match_sequence = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts" / "pass_sequence_matching.py")
)["match_sequence"]


def event(
    passer: str = "A", passed: str = "B", lap: int = 5, t_s: float | None = None
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "passer_code": passer,
        "passed_code": passed,
        "lap_number": lap,
    }
    if t_s is not None:
        result["t_s"] = t_s
    return result


def test_empty_sequences() -> None:
    assert match_sequence([], []) == {
        "matches": [],
        "unmatched_expected_indices": [],
        "unmatched_observed_indices": [],
    }
    assert match_sequence([], [event(t_s=1)])["unmatched_observed_indices"] == [0]
    assert match_sequence([event()], [])["unmatched_expected_indices"] == [0]


def test_chronological_sort_preserves_original_indices_and_inputs() -> None:
    expected = [event(), event("B", "A")]
    observed = [event("B", "A", t_s=20), event(t_s=10)]
    before = deepcopy((expected, observed))
    assert match_sequence(expected, observed)["matches"] == [
        {"expected_index": 0, "observed_index": 1},
        {"expected_index": 1, "observed_index": 0},
    ]
    assert (expected, observed) == before


def test_reverse_sequence_prefers_earliest_observation() -> None:
    result = match_sequence(
        [event(), event("B", "A")],
        [event("B", "A", t_s=1), event(t_s=2)],
    )
    assert result == {
        "matches": [{"expected_index": 1, "observed_index": 0}],
        "unmatched_expected_indices": [0],
        "unmatched_observed_indices": [1],
    }


def test_duplicates_are_not_reused_and_ties_are_deterministic() -> None:
    expected = [event(), event(), event()]
    observed = [event(t_s=3), event(t_s=1)]
    result = match_sequence(expected, observed)
    assert result["matches"] == [
        {"expected_index": 0, "observed_index": 1},
        {"expected_index": 1, "observed_index": 0},
    ]
    assert result["unmatched_expected_indices"] == [2]
    assert result == match_sequence(expected, observed)


def test_direction_is_not_interchangeable() -> None:
    assert not match_sequence([event()], [event("B", "A", t_s=1)])["matches"]


@pytest.mark.parametrize("difference, count", [(-2, 0), (-1, 1), (0, 1), (1, 1), (2, 0)])
def test_lap_tolerance_boundary(difference: int, count: int) -> None:
    assert len(match_sequence([event()], [event(lap=5 + difference, t_s=1)], 1)["matches"]) == count


def test_exact_lap_is_default() -> None:
    assert not match_sequence([event()], [event(lap=6, t_s=1)])["matches"]


def test_dynamic_programming_beats_greedy_reference_assignment() -> None:
    # Taking the first reference's available A->B would discard both B->A passes.
    result = match_sequence(
        [event(), event("B", "A"), event("B", "A")],
        [event("B", "A", t_s=1), event("B", "A", t_s=2), event(t_s=3)],
    )
    assert result["matches"] == [
        {"expected_index": 1, "observed_index": 0},
        {"expected_index": 2, "observed_index": 1},
    ]


@pytest.mark.parametrize("value", [-1, True, False, 1.5, "1", None])
def test_invalid_tolerance(value: Any) -> None:
    with pytest.raises(ValueError, match="lap_tolerance"):
        match_sequence([], [], value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True, "1", None])
def test_invalid_timestamps(value: Any) -> None:
    observed = event(t_s=1)
    observed["t_s"] = value
    with pytest.raises(ValueError, match="t_s"):
        match_sequence([], [observed])


def test_missing_and_duplicate_timestamps() -> None:
    with pytest.raises(ValueError, match="t_s"):
        match_sequence([], [event()])
    with pytest.raises(ValueError, match="unique"):
        match_sequence([], [event(t_s=1), event("B", "A", t_s=1)])


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "1", None])
@pytest.mark.parametrize("side", ["expected", "observed"])
def test_invalid_laps(value: Any, side: str) -> None:
    invalid = event(t_s=1)
    invalid["lap_number"] = value
    with pytest.raises(ValueError, match="lap_number"):
        match_sequence(
            [invalid] if side == "expected" else [], [invalid] if side == "observed" else []
        )


@pytest.mark.parametrize("passer, passed", [("", "B"), ("A", " "), (None, "B"), ("A", "A")])
def test_invalid_driver_codes(passer: Any, passed: Any) -> None:
    with pytest.raises(ValueError):
        match_sequence([event(passer, passed)], [])
