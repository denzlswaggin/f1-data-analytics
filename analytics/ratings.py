"""Global teammate-normalised "true pace" driver rating.

Teammate qualifying gaps are pairwise and local (driver vs their teammate). To
turn them into a single cross-era leaderboard we solve for a per-driver *pace
deficit* ``d_i`` (log-% units, lower = faster) that best explains every observed
gap::

    minimise  sum over comparisons ( d_i - d_j - gap_ij )^2

This is a Massey-style least-squares rating on the teammate graph. The gap is
antisymmetric and additive, so the fit chains skill across drivers who never
shared a car (Hamilton -> Rosberg -> Bottas -> Russell -> Verstappen -> ...).
The solution is identified only up to an additive constant, so we centre it
(mean = 0) within the largest connected component of the teammate graph;
ratings are only comparable inside a connected component.

The solver is damped Jacobi iteration on the normal equations: repeatedly set
each driver's deficit toward the mean of ``d_teammate + gap`` over their
comparisons, under-relax, recentre, and iterate to convergence.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from ingestion.logging import get_logger

log = get_logger(__name__)


class _UnionFind:
    """Minimal union-find for locating connected components of drivers."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self._parent.setdefault(x, x)
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        # Path compression.
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[ra] = rb


@dataclass(frozen=True)
class RatingResult:
    """Ratings frame plus solver diagnostics."""

    ratings: pd.DataFrame
    iterations: int
    converged: bool
    main_component_size: int


def largest_component(gaps: pd.DataFrame) -> set[str]:
    """Return driver IDs in the largest connected teammate component."""
    uf = _UnionFind()
    for driver, teammate in zip(gaps["driver_id"], gaps["teammate_id"], strict=True):
        uf.union(driver, teammate)
    members: dict[str, list[str]] = {}
    drivers = pd.unique(pd.concat([gaps["driver_id"], gaps["teammate_id"]]))
    for d in drivers:
        members.setdefault(uf.find(d), []).append(d)
    largest = max(members.values(), key=len)
    return set(largest)


def compute_ratings(
    gaps: pd.DataFrame,
    max_iter: int = 2000,
    tol: float = 1e-10,
    prior_weight: float = 8.0,
    damping: float = 0.5,
) -> RatingResult:
    """Solve for per-driver pace deficits from directed teammate gaps.

    ``gaps`` needs columns ``driver_id``, ``teammate_id``, ``pace_gap`` (one row
    per driver per comparison; the mirror row is expected to be present too).

    ``prior_weight`` adds empirical-Bayes shrinkage: a ridge term that pulls each
    driver's deficit toward the field mean as if they had ``prior_weight`` extra
    comparisons at rating 0. This stops drivers with very few teammate races (and
    thin chains to the rest of the grid) from topping the leaderboard on noise.
    Set to 0 for the pure least-squares fit.
    """
    required = {"driver_id", "teammate_id", "pace_gap"}
    missing = required - set(gaps.columns)
    if missing:
        raise ValueError(f"gaps is missing columns: {sorted(missing)}")

    if gaps.empty:
        empty = pd.DataFrame(
            columns=["driver_id", "n_comparisons", "pace_deficit", "rating", "rank"]
        )
        return RatingResult(empty, 0, True, 0)

    main = largest_component(gaps)
    g = gaps[gaps["driver_id"].isin(main) & gaps["teammate_id"].isin(main)].copy()

    drivers = np.array(sorted(main))
    idx = {d: i for i, d in enumerate(drivers)}
    di = g["driver_id"].map(idx).to_numpy()
    dj = g["teammate_id"].map(idx).to_numpy()
    gap = g["pace_gap"].to_numpy(dtype=float)

    n = len(drivers)
    counts = np.bincount(di, minlength=n).astype(float)
    # Ridge denominator: real comparisons + pseudo-comparisons at rating 0.
    denom = counts + prior_weight
    denom[denom == 0] = 1.0  # avoid divide-by-zero for isolated nodes

    deficit = np.zeros(n, dtype=float)
    converged = False
    iterations = 0
    for iterations in range(1, max_iter + 1):  # noqa: B007 (final value used below)
        # Each comparison implies d_i ~= d_teammate + gap; the prior implies 0.
        estimate = deficit[dj] + gap
        summed = np.bincount(di, weights=estimate, minlength=n)
        target = summed / denom
        # Damped (under-relaxed) update. Plain Jacobi oscillates on bipartite
        # sub-graphs (e.g. a two-driver chain); damping guarantees convergence.
        new_deficit = (1 - damping) * deficit + damping * target
        if prior_weight == 0:
            new_deficit -= new_deficit.mean()  # fix the additive gauge
        delta = float(np.max(np.abs(new_deficit - deficit)))
        deficit = new_deficit
        if delta < tol:
            converged = True
            break

    n_comparisons = np.bincount(di, minlength=n)
    out = pd.DataFrame(
        {
            "driver_id": drivers,
            "n_comparisons": n_comparisons,
            "pace_deficit": deficit,
            # Higher rating = faster (nicer for a leaderboard).
            "rating": -deficit,
        }
    )
    out = out.sort_values("rating", ascending=False, ignore_index=True)
    out["rank"] = out.index + 1

    log.info(
        "ratings.solved",
        drivers=n,
        comparisons=len(g),
        iterations=iterations,
        converged=converged,
    )
    return RatingResult(out, iterations, converged, len(main))
