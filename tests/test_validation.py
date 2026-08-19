"""Tests for the rating-validation checks (pure functions on synthetic gaps)."""

from __future__ import annotations

import math

import pandas as pd
import pytest
from analytics.validation import (
    backtest_ratings,
    bootstrap_ratings,
    shrinkage_sensitivity,
)


def _chain_gaps(order: list[str], seasons: range) -> pd.DataFrame:
    """Directed teammate gaps for a fixed skill chain (order = fastest → slowest).

    Consecutive drivers are teammates; pair ``i`` has a gap of ``-(i+1)`` for the
    faster driver (and the mirror), so the true ordering is unambiguous and the
    per-pair magnitudes vary (giving the backtest something to correlate on).
    """
    rows = []
    for season in seasons:
        for i in range(len(order) - 1):
            fast, slow = order[i], order[i + 1]
            step = float(i + 1)
            rows.append(
                {"driver_id": fast, "teammate_id": slow, "pace_gap": -step, "season": season}
            )
            rows.append(
                {"driver_id": slow, "teammate_id": fast, "pace_gap": step, "season": season}
            )
    return pd.DataFrame(rows)


def test_missing_columns_raise() -> None:
    with pytest.raises(ValueError, match="missing columns"):
        backtest_ratings(pd.DataFrame({"driver_id": ["a"], "teammate_id": ["b"]}))


def test_backtest_recovers_a_clean_signal() -> None:
    gaps = _chain_gaps(["a", "b", "c", "d"], range(2000, 2011))
    bt = backtest_ratings(gaps, min_train_seasons=5)
    assert bt.n_predictions > 0
    assert bt.n_test_seasons == 6  # seasons 2005..2010
    # The faster driver is predicted faster every time, per race and per season.
    assert bt.sign_accuracy == 1.0
    assert bt.pair_sign_accuracy == 1.0
    assert bt.pearson_r > 0.0  # per-pair magnitudes vary and line up in direction


def test_backtest_too_few_seasons_yields_no_predictions() -> None:
    gaps = _chain_gaps(["a", "b"], range(2000, 2003))  # 3 seasons < min_train_seasons
    bt = backtest_ratings(gaps, min_train_seasons=5)
    assert bt.n_predictions == 0
    assert math.isnan(bt.sign_accuracy)


def test_shrinkage_default_is_identity_and_ratings_shrink() -> None:
    gaps = _chain_gaps(["a", "b", "c", "d"], range(2000, 2006))
    sens = shrinkage_sensitivity(gaps, prior_weights=(0.0, 4.0, 8.0, 32.0), default=8.0, top_n=2)
    row = sens.set_index("prior_weight")
    # Compared against itself the default is a perfect match.
    assert row.loc[8.0, "spearman_vs_default"] == pytest.approx(1.0)
    assert row.loc[8.0, "top_n_overlap"] == pytest.approx(1.0)
    # A tighter prior pulls ratings toward zero.
    assert row.loc[32.0, "mean_abs_rating"] < row.loc[0.0, "mean_abs_rating"]


def test_bootstrap_is_deterministic_and_brackets_the_estimate() -> None:
    gaps = _chain_gaps(["a", "b", "c", "d"], range(2000, 2006))
    ci_a = bootstrap_ratings(gaps, n_boot=40, seed=7)
    ci_b = bootstrap_ratings(gaps, n_boot=40, seed=7)
    pd.testing.assert_frame_equal(ci_a, ci_b)  # same seed -> same result
    assert set(ci_a.columns) == {"driver_id", "rating", "rating_lo", "rating_hi", "n_boot"}
    assert not ci_a.empty
    # Each point estimate lies within its own confidence band.
    assert (ci_a["rating_lo"] <= ci_a["rating"]).all()
    assert (ci_a["rating"] <= ci_a["rating_hi"]).all()
