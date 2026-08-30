"""Tests for the experimental joint qualifying/race-pace model."""

from __future__ import annotations

import pandas as pd
from analytics.ratings_v3 import (
    V3Parameters,
    bootstrap_joint_intervals,
    evaluate_v3_experiment,
    fit_joint_ratings,
)
from pandas.testing import assert_frame_equal


def _gaps(
    seasons: range,
    *,
    qualifying_gap: float = -1.0,
    race_gap: float = -0.5,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    qualifying: list[dict[str, object]] = []
    race: list[dict[str, object]] = []
    for season in seasons:
        for rnd in range(1, 4):
            for driver, teammate, direction in (("A", "B", 1.0), ("B", "A", -1.0)):
                common = {
                    "race_key": f"{season}_{rnd}",
                    "season": season,
                    "driver_id": driver,
                    "teammate_id": teammate,
                }
                qualifying.append(
                    {**common, "pace_gap": qualifying_gap * direction, "common_session": "Q3"}
                )
                race.append({**common, "pace_gap": race_gap * direction, "n_laps": 20})
    return pd.DataFrame(qualifying), pd.DataFrame(race)


def test_joint_fit_keeps_disciplines_distinct_but_partially_pooled() -> None:
    qualifying, race = _gaps(range(2022, 2025), qualifying_gap=-2.0, race_gap=2.0)
    independent = fit_joint_ratings(
        qualifying,
        race,
        parameters=V3Parameters(0.5, 1.0, 0.0, 1.0),
    ).ratings
    pooled = fit_joint_ratings(
        qualifying,
        race,
        parameters=V3Parameters(0.5, 1.0, 20.0, 1.0),
    ).ratings

    independent_a = independent[independent["driver_id"] == "A"].iloc[-1]
    pooled_a = pooled[pooled["driver_id"] == "A"].iloc[-1]
    assert independent_a["quali_rating"] > 0
    assert independent_a["race_rating"] < 0
    assert pooled_a["quali_rating"] > pooled_a["race_rating"]
    assert abs(pooled_a["discipline_delta"]) < abs(independent_a["discipline_delta"])


def test_bootstrap_is_clustered_deterministic_and_contains_point_rating() -> None:
    qualifying, race = _gaps(range(2020, 2024))
    first = bootstrap_joint_intervals(qualifying, race, n_boot=12, seed=17)
    second = bootstrap_joint_intervals(qualifying, race, n_boot=12, seed=17)
    point = fit_joint_ratings(qualifying, race).ratings

    assert_frame_equal(first, second)
    merged = point.merge(first, on=["driver_id", "season"])
    assert (merged["rating_lo"] <= merged["rating"]).all()
    assert (merged["rating"] <= merged["rating_hi"]).all()
    assert (merged["n_boot"] == 12).all()


def test_experiment_reserves_2026_and_emits_calibration_and_ablations() -> None:
    qualifying, race = _gaps(range(2019, 2027))
    result = evaluate_v3_experiment(
        qualifying,
        race,
        final_holdout_season=2026,
        min_train_seasons=3,
        n_boot=8,
        seed=4,
    )

    assert result.holdout_status == "evaluated"
    assert {"nested_validation", "final_holdout_2026"} <= set(result.validation["split"])
    holdout = result.validation[result.validation["split"] == "final_holdout_2026"]
    assert (holdout["status"] == "evaluated").all()
    assert holdout["interval_coverage"].notna().all()
    assert holdout["mean_interval_width"].notna().all()
    assert {
        "static_v1_by_discipline",
        "dynamic_v2_by_discipline",
        "v3_no_cross_pooling",
        "v3_no_temporal_pooling",
        "v3_tuned",
    } <= set(result.ablation["model"])


def test_holdout_outcomes_cannot_change_selected_parameters() -> None:
    qualifying, race = _gaps(range(2019, 2027))
    changed_q = qualifying.copy()
    changed_r = race.copy()
    changed_q.loc[changed_q["season"] == 2026, "pace_gap"] *= -8
    changed_r.loc[changed_r["season"] == 2026, "pace_gap"] *= -8

    first = evaluate_v3_experiment(qualifying, race, n_boot=4)
    second = evaluate_v3_experiment(changed_q, changed_r, n_boot=4)

    assert first.selected_parameters == second.selected_parameters
    first_holdout = first.validation[first.validation["split"] == "final_holdout_2026"]
    second_holdout = second.validation[second.validation["split"] == "final_holdout_2026"]
    assert float(first_holdout.iloc[0]["mae"]) != float(second_holdout.iloc[0]["mae"])


def test_missing_final_holdout_is_explicit_not_an_error() -> None:
    qualifying, race = _gaps(range(2019, 2026))
    result = evaluate_v3_experiment(qualifying, race, n_boot=4)

    assert result.holdout_status == "not_available"
    unavailable = result.validation[result.validation["split"] == "final_holdout_2026"]
    assert len(unavailable) == 1
    assert unavailable.iloc[0]["status"] == "not_available"
    assert int(unavailable.iloc[0]["n_predictions"]) == 0
    assert result.recommended_for_promotion is False
