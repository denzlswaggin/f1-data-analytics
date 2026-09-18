"""Tests for the Saturday-vs-Sunday pace profile (pure, offline)."""

from __future__ import annotations

import pandas as pd
import pytest
from analytics.pace_profile import PROFILE_COLUMNS, build_pace_profile
from analytics.ratings import compute_ratings


def _gaps(pairs: list[tuple[str, str, float]], seasons: list[int]) -> pd.DataFrame:
    """Build a gaps frame over ``seasons``, adding each row's antisymmetric mirror."""
    rows = []
    for season in seasons:
        for driver, teammate, gap in pairs:
            rows.append(
                {
                    "driver_id": driver,
                    "teammate_id": teammate,
                    "pace_gap": gap,
                    "season": season,
                }
            )
            rows.append(
                {
                    "driver_id": teammate,
                    "teammate_id": driver,
                    "pace_gap": -gap,
                    "season": season,
                }
            )
    return pd.DataFrame(rows)


def test_delta_ranks_the_racer_above_the_qualifying_specialist() -> None:
    # Quali: A beats B by 2, B beats C by 2  -> ratings A=+2, B=0, C=-2.
    quali = _gaps([("A", "B", -2.0), ("B", "C", -2.0)], [2024])
    # Race: A is 1 SLOWER than B, B beats C by 4 -> ratings A=+2/3, B=+5/3, C=-7/3.
    race = _gaps([("A", "B", 1.0), ("B", "C", -4.0)], [2024])

    result = build_pace_profile(quali, race, prior_weight=0.0)
    profile = result.profile

    assert list(profile.columns) == PROFILE_COLUMNS
    # B gains most on Sunday; A loses most.
    assert list(profile["driver_id"]) == ["B", "C", "A"]
    assert list(profile["delta_rank"]) == [1, 2, 3]

    d = profile.set_index("driver_id")
    assert d.loc["B", "delta"] == pytest.approx(5 / 3, abs=1e-6)
    assert d.loc["C", "delta"] == pytest.approx(-1 / 3, abs=1e-6)
    assert d.loc["A", "delta"] == pytest.approx(-4 / 3, abs=1e-6)
    # delta is exactly the difference of the two ratings.
    assert (d["race_rating"] - d["quali_rating"]).sub(d["delta"]).abs().max() < 1e-12


def test_quali_gaps_are_matched_to_the_race_seasons() -> None:
    """The whole point of the module: never compare ratings fitted on different eras."""
    # A dominates B in 2020 but is beaten by B in 2024.
    quali = pd.concat(
        [
            _gaps([("A", "B", -5.0), ("B", "C", -1.0)], [2020]),
            _gaps([("A", "B", 3.0), ("B", "C", -1.0)], [2024]),
        ],
        ignore_index=True,
    )
    # Race pace only exists for 2024, so only 2024 qualifying may be used.
    race = _gaps([("A", "B", 1.0), ("B", "C", -1.0)], [2024])

    result = build_pace_profile(quali, race, prior_weight=0.0)
    assert result.seasons == [2024]

    quali_2024_only = compute_ratings(
        quali[quali["season"] == 2024], prior_weight=0.0
    ).ratings.set_index("driver_id")["rating"]
    got = result.profile.set_index("driver_id")["quali_rating"]
    assert got.sub(quali_2024_only).abs().max() == pytest.approx(0.0, abs=1e-9)

    # Sanity: pooling 2020 in would have made A the fastest qualifier, not B.
    pooled = compute_ratings(quali, prior_weight=0.0).ratings.set_index("driver_id")["rating"]
    assert pooled["A"] > pooled["B"]
    assert got["B"] > got["A"]


def test_drivers_without_both_halves_are_dropped() -> None:
    quali = _gaps([("A", "B", -1.0), ("B", "C", -1.0), ("C", "D", -1.0)], [2024])
    race = _gaps([("A", "B", -1.0), ("B", "C", -1.0)], [2024])  # no D

    profile = build_pace_profile(quali, race, prior_weight=0.0).profile
    assert set(profile["driver_id"]) == {"A", "B", "C"}
    # Ranks are recomputed over the joined population, so they stay contiguous.
    assert sorted(profile["quali_rank"]) == [1, 2, 3]
    assert sorted(profile["race_rank"]) == [1, 2, 3]


def test_missing_columns_raise_and_name_the_frame() -> None:
    good = _gaps([("A", "B", -1.0)], [2024])
    bad = good.drop(columns=["season"])
    with pytest.raises(ValueError, match="race_gaps is missing columns"):
        build_pace_profile(good, bad)
    with pytest.raises(ValueError, match="quali_gaps is missing columns"):
        build_pace_profile(bad, good)


def test_empty_race_gaps_yield_an_empty_profile() -> None:
    quali = _gaps([("A", "B", -1.0)], [2024])
    empty = pd.DataFrame(columns=["driver_id", "teammate_id", "pace_gap", "season"])

    result = build_pace_profile(quali, empty)
    assert result.profile.empty
    assert list(result.profile.columns) == PROFILE_COLUMNS
    assert result.seasons == []


def test_joint_bootstrap_preserves_identical_weekend_effects() -> None:
    from analytics.pace_profile import bootstrap_pace_difference

    rows = []
    for season in (2024, 2025):
        for rnd in range(6):
            for driver, teammate, sign in (("a", "b", 1), ("b", "a", -1)):
                rows.append(
                    {
                        "season": season,
                        "race_key": f"{season}-{rnd}",
                        "driver_id": driver,
                        "teammate_id": teammate,
                        "pace_gap": sign * (rnd + 1) / 10,
                    }
                )
    gaps = pd.DataFrame(rows)
    intervals = bootstrap_pace_difference(gaps, gaps, samples=30)
    assert intervals.interval_eligible.all()
    assert (intervals.bootstrap_valid_samples == 30).all()
    assert (intervals[["delta_lo", "delta_hi"]] == 0).all().all()
    pd.testing.assert_frame_equal(intervals, bootstrap_pace_difference(gaps, gaps, samples=30))
