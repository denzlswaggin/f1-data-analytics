"""Tests for clean-air driver pace consistency and slow-tail evidence."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd
import pytest
from analytics.pace_consistency import analyse_pace_consistency


def _stint(
    driver: str = "AAA",
    *,
    stint: int = 1,
    start_lap: int = 2,
    count: int = 8,
    slope: float = 0.10,
    intercept: float = 0.30,
    residuals: list[float] | None = None,
    coverage: float = 100.0,
    compound: str = "MEDIUM",
) -> pd.DataFrame:
    errors = residuals or [0.0] * count
    rows: list[dict[str, object]] = []
    for offset in range(count):
        tyre_life = float(offset + 2)
        rows.append(
            {
                "season": 2026,
                "round": 1,
                "race_name": "Test Grand Prix",
                "driver_code": driver,
                "driver_name": f"Driver {driver}",
                "team": f"Team {driver}",
                "lap_number": start_lap + offset,
                "stint": stint,
                "compound": compound,
                "tyre_life": tyre_life,
                "lap_time_sec": 100.0 + slope * tyre_life + errors[offset],
                "air_state": "clean_air",
                "replay_coverage_pct": coverage,
                "controlled_pace_delta_sec": intercept + slope * tyre_life + errors[offset],
            }
        )
    return pd.DataFrame(rows)


def test_exact_stint_trend_has_zero_dispersion_and_tail() -> None:
    result = analyse_pace_consistency(_stint())

    driver = result.summary.iloc[0]
    assert bool(driver["consistency_eligible"])
    assert driver["modelled_laps"] == 8
    assert driver["modelled_stints"] == 1
    assert driver["robust_consistency_sec"] == pytest.approx(0.0)
    assert driver["p90_slow_tail_sec"] == pytest.approx(0.0)
    assert driver["unexplained_slow_laps"] == 0
    assert driver["unexplained_slow_lap_cost_sec"] == pytest.approx(0.0)
    assert driver["confidence"] == "low"
    assert set(result.laps["stint_slope_sec_per_tyre_lap"].round(8)) == {0.1}
    assert np.allclose(result.laps["pace_residual_sec"], 0.0)


def test_robust_fit_keeps_one_slow_tail_outlier_visible() -> None:
    laps = _stint(residuals=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 2.0])

    result = analyse_pace_consistency(laps)

    driver = result.summary.iloc[0]
    final_lap = result.laps.iloc[-1]
    expected_excess = 2.0 - driver["slow_lap_threshold_sec"]
    assert final_lap["pace_residual_sec"] == pytest.approx(2.0)
    assert bool(final_lap["is_unexplained_slow_lap"])
    assert final_lap["unexplained_slow_excess_sec"] == pytest.approx(expected_excess)
    assert driver["unexplained_slow_laps"] == 1
    assert driver["unexplained_slow_lap_share_pct"] == pytest.approx(12.5)
    assert driver["unexplained_slow_lap_cost_sec"] == pytest.approx(expected_excess)
    assert driver["slow_lap_cost_per_10_laps_sec"] == pytest.approx(10 * expected_excess / 8)


def test_separate_stint_trends_are_removed_before_pooling() -> None:
    residuals = [-0.2, 0.1, 0.0, 0.2, -0.1]
    first = _stint(count=5, residuals=residuals)
    second = _stint(
        stint=2,
        start_lap=20,
        count=5,
        slope=0.35,
        intercept=-1.5,
        residuals=residuals,
        compound="HARD",
    )

    combined = analyse_pace_consistency(pd.concat([first, second], ignore_index=True))
    reference = analyse_pace_consistency(first, min_publish_laps=5)

    driver = combined.summary.iloc[0]
    assert driver["modelled_stints"] == 2
    assert driver["robust_consistency_sec"] == pytest.approx(
        reference.summary.iloc[0]["robust_consistency_sec"]
    )


@pytest.mark.parametrize("air_state", ["traffic", "mixed"])
def test_non_clean_outlier_is_excluded_from_denominator(air_state: str) -> None:
    laps = _stint(count=9, residuals=[0.0] * 8 + [10.0])
    laps.loc[laps.index[-1], "air_state"] = air_state

    result = analyse_pace_consistency(laps)

    driver = result.summary.iloc[0]
    excluded = result.laps.iloc[-1]
    assert driver["modelled_laps"] == 8
    assert driver["unexplained_slow_laps"] == 0
    assert not bool(excluded["lap_eligible"])
    assert excluded["lap_exclusion_reason"] in {"traffic_exposed", "mixed_air"}


def test_under_covered_and_incomplete_laps_are_excluded() -> None:
    laps = _stint(count=10)
    laps.loc[8, "replay_coverage_pct"] = 79.9
    laps.loc[9, "controlled_pace_delta_sec"] = np.nan

    result = analyse_pace_consistency(laps)

    assert result.summary.iloc[0]["modelled_laps"] == 8
    reasons = result.laps.set_index("lap_number")["lap_exclusion_reason"]
    assert reasons.loc[10] == "replay_under_covered"
    assert reasons.loc[11] == "missing_or_invalid_timing"


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda frame: frame.iloc[:4].copy(), "insufficient_stint_clean_laps"),
        (
            lambda frame: frame.assign(tyre_life=[2.0, 2.0, 3.0, 3.0, 4.0, 4.0, 4.0, 4.0]),
            "insufficient_tyre_age_variation",
        ),
        (
            lambda frame: frame.assign(tyre_life=[2.0, 2.5, 3.0, 3.5, 4.0, 4.0, 4.0, 4.0]),
            "insufficient_tyre_age_span",
        ),
    ],
)
def test_invalid_stint_shape_is_reported(
    mutate: Callable[[pd.DataFrame], pd.DataFrame], reason: str
) -> None:
    laps = mutate(_stint())

    result = analyse_pace_consistency(laps)

    assert not bool(result.summary.iloc[0]["consistency_eligible"])
    candidate = result.laps.loc[result.laps["air_state"].eq("clean_air")]
    assert set(candidate["lap_exclusion_reason"]) == {reason}


def test_compound_change_invalidates_stint_without_filtering_high_variance() -> None:
    changed = _stint()
    changed.loc[changed.index[-1], "compound"] = "HARD"
    invalid = analyse_pace_consistency(changed)
    assert set(invalid.laps["lap_exclusion_reason"]) == {"compound_changed_within_stint"}

    scattered = _stint(residuals=[-2.0, 2.0, -1.5, 1.5, -1.0, 1.0, -0.5, 0.5])
    valid = analyse_pace_consistency(scattered)
    assert bool(valid.summary.iloc[0]["consistency_eligible"])
    assert valid.summary.iloc[0]["robust_consistency_sec"] > 0


@pytest.mark.parametrize(
    ("lap_count", "stints", "coverage", "expected"),
    [(8, 1, 100.0, "low"), (16, 1, 90.0, "medium"), (20, 2, 95.0, "high")],
)
def test_confidence_uses_samples_stints_and_coverage(
    lap_count: int, stints: int, coverage: float, expected: str
) -> None:
    if stints == 1:
        laps = _stint(count=lap_count, coverage=coverage)
    else:
        laps = pd.concat(
            [
                _stint(count=lap_count // 2, coverage=coverage),
                _stint(stint=2, start_lap=30, count=lap_count // 2, coverage=coverage),
            ],
            ignore_index=True,
        )

    result = analyse_pace_consistency(laps)

    assert result.summary.iloc[0]["confidence"] == expected


def test_threshold_scales_with_lap_length_and_is_strict() -> None:
    laps = _stint(count=8)
    laps["lap_time_sec"] = 120.0
    result = analyse_pace_consistency(laps)
    assert result.summary.iloc[0]["slow_lap_threshold_sec"] == pytest.approx(1.2)

    # Exercise the public threshold settings with a robust +0.75 second tail.
    equality = _stint(residuals=[0.0] * 7 + [0.75])
    equal_result = analyse_pace_consistency(
        equality, slow_lap_floor_sec=0.75, slow_lap_lap_time_share=0.0001
    )
    assert equal_result.summary.iloc[0]["unexplained_slow_laps"] == 0


def test_validates_schema_parameters_duplicates_and_empty_output() -> None:
    laps = _stint()
    with pytest.raises(ValueError, match="missing columns"):
        analyse_pace_consistency(laps.drop(columns="air_state"))
    with pytest.raises(ValueError, match="thresholds"):
        analyse_pace_consistency(laps, min_stint_clean_laps=2)
    with pytest.raises(ValueError, match="coverage"):
        analyse_pace_consistency(laps, min_replay_coverage_pct=101)
    with pytest.raises(ValueError, match="slow-lap"):
        analyse_pace_consistency(laps, slow_lap_floor_sec=0)
    with pytest.raises(ValueError, match="duplicate"):
        analyse_pace_consistency(pd.concat([laps, laps.iloc[[0]]], ignore_index=True))

    empty = analyse_pace_consistency(laps.iloc[0:0])
    assert empty.summary.empty and empty.laps.empty
    assert str(empty.summary["consistency_eligible"].dtype) == "boolean"
    assert str(empty.laps["pace_residual_sec"].dtype) == "float64"
