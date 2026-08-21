"""Saturday vs Sunday — pairing the qualifying and race-pace driver ratings.

The headline rating (:mod:`analytics.ratings`) is built from *qualifying*
teammate gaps: one clean lap, no traffic, no fuel, no tyre management. It says
who is fastest on Saturday and nothing about Sunday.

``int_teammate_race_gaps`` supplies the race-pace counterpart in the same units
and at the same grain, so the *same* solver produces a second rating. Setting the
two side by side gives one debatable number per driver::

    delta = race_rating - quali_rating

Positive = gains ground relative to the field once the race starts (a racer);
negative = flatters to deceive on Saturday (a qualifying specialist). Both solves
are centred by the same empirical-Bayes gauge and share the log-% scale, so the
delta reads as "improves from Saturday to Sunday *more than the average driver
does*" — it is a relative claim, not an absolute one.

The qualifying gaps are deliberately **re-solved over only the seasons the race
gaps cover**, rather than reusing ``marts.driver_ratings``. Race pace comes from
FastF1 (2018+, and in practice a narrower ingested window) while qualifying goes
back to 2006; comparing ratings fitted on two different driver populations would
make the delta meaningless. Deriving the season set from ``race_gaps`` here —
instead of relying on two matching SQL filters — makes that impossible to get
wrong.

Pure: DataFrames in, DataFrame out, no warehouse I/O, so it unit-tests on tiny
synthetic gap sets.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from ingestion.logging import get_logger

from analytics.ratings import RatingResult, compute_ratings

log = get_logger(__name__)

_REQUIRED = {"driver_id", "teammate_id", "pace_gap", "season"}

PROFILE_COLUMNS = [
    "driver_id",
    "quali_rating",
    "race_rating",
    "delta",
    "quali_rank",
    "race_rank",
    "delta_rank",
    "n_quali_comparisons",
    "n_race_comparisons",
]


@dataclass(frozen=True)
class PaceProfileResult:
    """The joined profile plus both underlying solves' diagnostics."""

    profile: pd.DataFrame
    quali: RatingResult
    race: RatingResult
    seasons: list[int]


def _check(gaps: pd.DataFrame, name: str) -> None:
    missing = _REQUIRED - set(gaps.columns)
    if missing:
        raise ValueError(f"{name} is missing columns: {sorted(missing)}")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=PROFILE_COLUMNS)


def build_pace_profile(
    quali_gaps: pd.DataFrame,
    race_gaps: pd.DataFrame,
    prior_weight: float = 8.0,
) -> PaceProfileResult:
    """Solve both ratings on a matched season set and join them into one profile.

    Both frames need ``driver_id``, ``teammate_id``, ``pace_gap`` and ``season``
    (the grain of ``int_teammate_quali_gaps`` / ``int_teammate_race_gaps``, both
    directions of each pairing present).

    ``quali_gaps`` is filtered to the seasons present in ``race_gaps`` before
    solving, so the two ratings describe the same population. Only drivers who
    survive *both* solves — each keeps its own largest connected component — get
    a row, since a delta needs both halves. Ranks are recomputed within that
    joined population rather than carried over from the separate solves.
    """
    _check(quali_gaps, "quali_gaps")
    _check(race_gaps, "race_gaps")

    seasons = sorted(int(s) for s in pd.unique(race_gaps["season"])) if not race_gaps.empty else []
    matched_quali = quali_gaps[quali_gaps["season"].isin(seasons)]

    quali = compute_ratings(matched_quali, prior_weight=prior_weight)
    race = compute_ratings(race_gaps, prior_weight=prior_weight)

    if quali.ratings.empty or race.ratings.empty:
        log.info("pace_profile.empty", quali=len(quali.ratings), race=len(race.ratings))
        return PaceProfileResult(_empty(), quali, race, seasons)

    q = quali.ratings.rename(
        columns={"rating": "quali_rating", "n_comparisons": "n_quali_comparisons"}
    )[["driver_id", "quali_rating", "n_quali_comparisons"]]
    r = race.ratings.rename(
        columns={"rating": "race_rating", "n_comparisons": "n_race_comparisons"}
    )[["driver_id", "race_rating", "n_race_comparisons"]]

    # Inner join: a driver needs both halves for the delta to mean anything.
    profile = q.merge(r, on="driver_id", how="inner")
    profile["delta"] = profile["race_rating"] - profile["quali_rating"]

    # Rank within the joined population, not within the separate solves, so the
    # three ranks are all over the same set of drivers.
    for column, rank_name in (
        ("quali_rating", "quali_rank"),
        ("race_rating", "race_rank"),
        ("delta", "delta_rank"),
    ):
        profile[rank_name] = (
            profile[column].rank(ascending=False, method="first").astype("int64")
        )

    profile = profile.sort_values("delta", ascending=False, ignore_index=True)
    profile = profile.loc[:, PROFILE_COLUMNS]

    log.info(
        "pace_profile.built",
        drivers=len(profile),
        seasons=len(seasons),
        quali_component=quali.main_component_size,
        race_component=race.main_component_size,
    )
    return PaceProfileResult(profile, quali, race, seasons)
