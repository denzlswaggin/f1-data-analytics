"""Tests for time-varying driver ratings."""

from __future__ import annotations

import pandas as pd
import pytest
from analytics.ratings_v2 import cluster_bootstrap_dynamic_ratings, compute_dynamic_ratings
from analytics.validation import compare_dynamic_backtest


def _season_gap(season: int, gap: float) -> list[dict[str, object]]:
    return [
        {"driver_id": "A", "teammate_id": "B", "pace_gap": gap, "season": season},
        {"driver_id": "B", "teammate_id": "A", "pace_gap": -gap, "season": season},
    ]


def test_dynamic_ratings_capture_form_change() -> None:
    gaps = pd.DataFrame(_season_gap(2022, -1.0) + _season_gap(2023, -0.2) + _season_gap(2024, 0.8))

    result = compute_dynamic_ratings(gaps, prior_weight=0.5, temporal_weight=1.0)
    ratings = result.ratings.set_index(["driver_id", "season"])

    assert result.converged
    assert ratings.loc[("A", 2022), "rating"] > ratings.loc[("B", 2022), "rating"]
    assert ratings.loc[("A", 2024), "rating"] < ratings.loc[("B", 2024), "rating"]
    assert ratings.loc[("A", 2024), "form_delta"] < 0


def test_temporal_weight_smooths_season_changes() -> None:
    gaps = pd.DataFrame(_season_gap(2023, -1.0) + _season_gap(2024, 1.0))

    flexible = compute_dynamic_ratings(gaps, prior_weight=0.5, temporal_weight=0.1).ratings
    smooth = compute_dynamic_ratings(gaps, prior_weight=0.5, temporal_weight=20.0).ratings

    flexible_a = flexible[flexible["driver_id"] == "A"].set_index("season")["rating"]
    smooth_a = smooth[smooth["driver_id"] == "A"].set_index("season")["rating"]
    assert abs(smooth_a.loc[2024] - smooth_a.loc[2023]) < abs(
        flexible_a.loc[2024] - flexible_a.loc[2023]
    )


def test_session_reliability_weights_affect_fit() -> None:
    gaps = pd.DataFrame(
        [
            {**row, "common_session": session}
            for row, session in zip(
                _season_gap(2024, -1.0) + _season_gap(2024, 0.5),
                ["Q3", "Q3", "Q1", "Q1"],
                strict=True,
            )
        ]
    )

    result = compute_dynamic_ratings(gaps, prior_weight=0.0, temporal_weight=0.0)

    assert result.ratings.set_index("driver_id").loc["A", "rating"] > 0


def test_dynamic_ratings_validate_input_and_empty_frame() -> None:
    with pytest.raises(ValueError, match="missing columns"):
        compute_dynamic_ratings(pd.DataFrame({"driver_id": ["A"]}))
    empty = pd.DataFrame(columns=["driver_id", "teammate_id", "pace_gap", "season"])
    assert compute_dynamic_ratings(empty).ratings.empty


def test_cluster_bootstrap_is_deterministic_and_keeps_mirrors_together() -> None:
    rows: list[dict[str, object]] = []
    for season in (2023, 2024):
        for race, gap in ((1, -1.0), (2, -0.5), (3, -0.8)):
            rows.extend({**row, "race_key": f"{season}-{race}"} for row in _season_gap(season, gap))
    gaps = pd.DataFrame(rows)

    first = cluster_bootstrap_dynamic_ratings(gaps, n_boot=20, seed=7)
    second = cluster_bootstrap_dynamic_ratings(gaps, n_boot=20, seed=7)

    pd.testing.assert_frame_equal(first, second)
    assert set(first.columns) == {"driver_id", "season", "rating_lo", "rating_hi", "n_boot"}
    assert (first["rating_lo"] <= first["rating_hi"]).all()
    assert (first["n_boot"] == 20).all()


def test_dynamic_backtest_improves_on_evolving_form() -> None:
    rows: list[dict[str, object]] = []
    for season in range(2000, 2012):
        gap = -1.2 + 0.2 * (season - 2000)
        rows.extend(_season_gap(season, gap))
    gaps = pd.DataFrame(rows)

    comparison = compare_dynamic_backtest(
        gaps,
        min_train_seasons=5,
        dynamic_prior_weight=0.2,
        temporal_weight=0.5,
    )

    assert comparison.n_predictions == 7
    assert comparison.dynamic_mae < comparison.static_mae
