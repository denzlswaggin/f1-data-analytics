"""Tests for the global driver-rating solver (pure, offline)."""

from __future__ import annotations

import pandas as pd
import pytest
from analytics.ratings import compute_ratings


def _directed(pairs: list[tuple[str, str, float]]) -> pd.DataFrame:
    """Build a gaps frame, adding the antisymmetric mirror of each row."""
    rows = []
    for driver, teammate, gap in pairs:
        rows.append({"driver_id": driver, "teammate_id": teammate, "pace_gap": gap})
        rows.append({"driver_id": teammate, "teammate_id": driver, "pace_gap": -gap})
    return pd.DataFrame(rows)


def test_linear_chain_recovers_known_deficits() -> None:
    # A faster than B by 1, B faster than C by 1 (pace_gap = d_driver - d_teammate).
    gaps = _directed([("A", "B", -1.0), ("B", "C", -1.0)])
    result = compute_ratings(gaps, prior_weight=0.0)
    assert result.converged

    r = result.ratings.set_index("driver_id")
    # Centred deficits: A=-1, B=0, C=+1  ->  ratings A=+1, B=0, C=-1.
    assert r.loc["A", "pace_deficit"] == pytest.approx(-1.0, abs=1e-6)
    assert r.loc["B", "pace_deficit"] == pytest.approx(0.0, abs=1e-6)
    assert r.loc["C", "pace_deficit"] == pytest.approx(1.0, abs=1e-6)
    assert list(result.ratings.sort_values("rank")["driver_id"]) == ["A", "B", "C"]


def test_shrinkage_pulls_low_sample_toward_zero() -> None:
    gaps = _directed([("A", "B", -2.0)])
    strong = compute_ratings(gaps, prior_weight=0.0).ratings.set_index("driver_id")
    shrunk = compute_ratings(gaps, prior_weight=10.0).ratings.set_index("driver_id")
    # With only one comparison, heavy shrinkage should shrink the spread.
    assert abs(shrunk.loc["A", "pace_deficit"]) < abs(strong.loc["A", "pace_deficit"])


def test_keeps_only_largest_connected_component() -> None:
    gaps = pd.concat(
        [
            _directed([("A", "B", -1.0), ("B", "C", -1.0)]),  # component of 3
            _directed([("D", "E", -1.0)]),  # component of 2
        ],
        ignore_index=True,
    )
    result = compute_ratings(gaps, prior_weight=0.0)
    ids = set(result.ratings["driver_id"])
    assert ids == {"A", "B", "C"}
    assert result.main_component_size == 3


def test_missing_columns_raises() -> None:
    with pytest.raises(ValueError, match="missing columns"):
        compute_ratings(pd.DataFrame({"driver_id": ["A"], "pace_gap": [0.1]}))


def test_empty_input_returns_empty() -> None:
    result = compute_ratings(pd.DataFrame(columns=["driver_id", "teammate_id", "pace_gap"]))
    assert result.ratings.empty
    assert result.converged
