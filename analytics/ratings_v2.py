"""Time-varying teammate-normalised driver ratings.

The baseline assigns one number to a driver's whole career. V2 instead creates
one node per driver-season and adds a temporal smoothness edge between adjacent
seasons. Race-weekend teammate gaps identify relative pace; temporal edges share
information across sparse seasons without forcing a driver's form to be static.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

import numpy as np
import pandas as pd
from ingestion.logging import get_logger

from analytics.ratings import largest_component

log = get_logger(__name__)

_REQUIRED = {"driver_id", "teammate_id", "pace_gap", "season"}


@dataclass(frozen=True)
class DynamicRatingResult:
    """Driver-season ratings plus iterative solver diagnostics."""

    ratings: pd.DataFrame
    iterations: int
    converged: bool
    main_component_size: int


def _observation_weights(gaps: pd.DataFrame) -> np.ndarray:
    """Return explicit weights, or conservative Q1/Q2/Q3 reliability weights."""
    if "weight" in gaps:
        weights = gaps["weight"].to_numpy(dtype=float)
    elif "common_session" in gaps:
        weights = (
            gaps["common_session"].map({"Q1": 0.8, "Q2": 0.9, "Q3": 1.0}).fillna(0.8).to_numpy()
        )
    else:
        weights = np.ones(len(gaps), dtype=float)
    if not np.isfinite(weights).all() or (weights <= 0).any():
        raise ValueError("observation weights must be finite and positive")
    return np.asarray(weights, dtype=float)


def compute_dynamic_ratings(
    gaps: pd.DataFrame,
    *,
    max_iter: int = 3000,
    tol: float = 1e-10,
    prior_weight: float = 4.0,
    temporal_weight: float = 12.0,
    damping: float = 0.5,
) -> DynamicRatingResult:
    """Fit a regularised pace deficit for every observed driver-season.

    The objective combines weighted teammate-gap error, a zero-centred ridge
    prior, and squared changes between consecutive observed seasons. Temporal
    links weaken across career gaps, so a comeback after several years can move
    more freely than adjacent seasons.
    """
    missing = _REQUIRED - set(gaps.columns)
    if missing:
        raise ValueError(f"gaps is missing columns: {sorted(missing)}")
    if prior_weight < 0 or temporal_weight < 0:
        raise ValueError("prior_weight and temporal_weight must be non-negative")
    if not 0 < damping <= 1:
        raise ValueError("damping must be in (0, 1]")
    if gaps.empty:
        columns = [
            "season",
            "rank",
            "driver_id",
            "rating",
            "pace_deficit",
            "form_delta",
            "n_comparisons",
        ]
        return DynamicRatingResult(pd.DataFrame(columns=columns), 0, True, 0)

    main = largest_component(gaps)
    frame = gaps[gaps["driver_id"].isin(main) & gaps["teammate_id"].isin(main)].copy()
    frame["season"] = frame["season"].astype(int)

    nodes = sorted(
        set(zip(frame["driver_id"].astype(str), frame["season"], strict=True))
        | set(zip(frame["teammate_id"].astype(str), frame["season"], strict=True))
    )
    node_index = {node: i for i, node in enumerate(nodes)}
    driver_node = np.fromiter(
        (
            node_index[(str(d), int(s))]
            for d, s in zip(frame["driver_id"], frame["season"], strict=True)
        ),
        dtype=int,
    )
    teammate_node = np.fromiter(
        (
            node_index[(str(d), int(s))]
            for d, s in zip(frame["teammate_id"], frame["season"], strict=True)
        ),
        dtype=int,
    )
    gap = frame["pace_gap"].to_numpy(dtype=float)
    weights = _observation_weights(frame)

    temporal_left: list[int] = []
    temporal_right: list[int] = []
    temporal_weights: list[float] = []
    seasons_by_driver: dict[str, list[int]] = {}
    for driver, season in nodes:
        seasons_by_driver.setdefault(driver, []).append(season)
    for driver, seasons in seasons_by_driver.items():
        ordered = sorted(seasons)
        for previous, current in pairwise(ordered):
            link_weight = temporal_weight / (current - previous)
            left, right = node_index[(driver, previous)], node_index[(driver, current)]
            temporal_left.extend([left, right])
            temporal_right.extend([right, left])
            temporal_weights.extend([link_weight, link_weight])

    n_nodes = len(nodes)
    ti = np.asarray(temporal_left, dtype=int)
    tj = np.asarray(temporal_right, dtype=int)
    tw = np.asarray(temporal_weights, dtype=float)
    denominator = np.bincount(driver_node, weights=weights, minlength=n_nodes) + prior_weight
    if len(ti):
        denominator += np.bincount(ti, weights=tw, minlength=n_nodes)
    denominator[denominator == 0] = 1.0

    deficit = np.zeros(n_nodes, dtype=float)
    converged = False
    iterations = 0
    for iterations in range(1, max_iter + 1):  # noqa: B007 (reported in diagnostics)
        estimates = weights * (deficit[teammate_node] + gap)
        total = np.bincount(driver_node, weights=estimates, minlength=n_nodes)
        if len(ti):
            total += np.bincount(ti, weights=tw * deficit[tj], minlength=n_nodes)
        target = total / denominator
        updated = (1 - damping) * deficit + damping * target
        delta = float(np.max(np.abs(updated - deficit)))
        deficit = updated
        if delta < tol:
            converged = True
            break

    counts = np.bincount(driver_node, minlength=n_nodes)
    ratings = pd.DataFrame(
        {
            "driver_id": [driver for driver, _ in nodes],
            "season": [season for _, season in nodes],
            "pace_deficit": deficit,
            "rating": -deficit,
            "n_comparisons": counts,
        }
    )
    ratings["rank"] = (
        ratings.groupby("season")["rating"].rank(method="first", ascending=False).astype(int)
    )
    ratings = ratings.sort_values(["driver_id", "season"], ignore_index=True)
    ratings["form_delta"] = ratings.groupby("driver_id")["rating"].diff()
    ratings = ratings.loc[
        :, ["season", "rank", "driver_id", "rating", "pace_deficit", "form_delta", "n_comparisons"]
    ].sort_values(["season", "rank"], ignore_index=True)

    log.info(
        "ratings_v2.solved",
        nodes=n_nodes,
        drivers=len(main),
        iterations=iterations,
        converged=converged,
    )
    return DynamicRatingResult(ratings, iterations, converged, len(main))
