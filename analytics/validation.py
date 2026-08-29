"""Validation of the teammate-normalised driver ratings.

The solver (:mod:`analytics.ratings`) fits per-driver pace deficits that best
explain observed teammate qualifying gaps. This module asks the harder question —
does that fit *generalise*? — with three pure checks over the same gap data:

- :func:`backtest_ratings` — expanding-window temporal hold-out. Fit on seasons
  ``< Y``, predict season ``Y``'s teammate gaps from the fitted deficits, and score
  sign accuracy / correlation / error against a naive predict-zero baseline.
- :func:`bootstrap_ratings` — resample the teammate comparisons with replacement,
  refit, and take percentile confidence intervals per driver, so a thin-sample
  driver's rating carries an honest uncertainty band.
- :func:`shrinkage_sensitivity` — sweep the empirical-Bayes ``prior_weight`` and
  measure how stable the leaderboard order is (Spearman vs the default).

Predicted gap for a pairing ``(i, j)`` is ``deficit_i - deficit_j`` — exactly the
quantity the solver drives toward ``pace_gap`` on the training edges.

All functions are pure (DataFrame in, DataFrame/dataclass out) so they unit-test
on tiny synthetic gap sets.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from ingestion.logging import get_logger

from analytics.ratings import compute_ratings
from analytics.ratings_v2 import compute_dynamic_ratings

log = get_logger(__name__)

_REQUIRED = {"driver_id", "teammate_id", "pace_gap", "season"}


def _check(gaps: pd.DataFrame) -> None:
    missing = _REQUIRED - set(gaps.columns)
    if missing:
        raise ValueError(f"gaps is missing columns: {sorted(missing)}")


def _dedupe_undirected(gaps: pd.DataFrame) -> pd.DataFrame:
    """Keep one directed row per comparison (the ``driver_id < teammate_id`` half).

    The gap data is antisymmetric — every comparison appears twice (i→j and j→i).
    Keeping one half avoids double-counting predictions and bootstrap edges.
    """
    return gaps[gaps["driver_id"] < gaps["teammate_id"]]


def _spearman(a: pd.Series, b: pd.Series) -> float:
    """Spearman rank correlation without a SciPy dependency.

    Spearman ``rho`` is just the Pearson correlation of the ranked values, so we
    rank (average ties) and hand the ranks to ``np.corrcoef``. ``pandas``' own
    ``method="spearman"`` imports ``scipy``, which is only in the heavy
    ``.[telemetry]`` extra — absent from the lean core/CI install.
    """
    ar = a.rank().to_numpy(dtype=float)
    br = b.rank().to_numpy(dtype=float)
    if len(ar) < 2:
        return float("nan")
    return float(np.corrcoef(ar, br)[0, 1])


def _make_directed(undirected: pd.DataFrame) -> pd.DataFrame:
    """Rebuild both directions (i→j and j→i, gap negated) for the solver."""
    fwd = undirected[["driver_id", "teammate_id", "pace_gap"]]
    rev = pd.DataFrame(
        {
            "driver_id": undirected["teammate_id"].to_numpy(),
            "teammate_id": undirected["driver_id"].to_numpy(),
            "pace_gap": -undirected["pace_gap"].to_numpy(),
        }
    )
    return pd.concat([fwd, rev], ignore_index=True)


@dataclass(frozen=True)
class BacktestResult:
    """Out-of-sample predictive metrics plus the per-pairing prediction frame."""

    n_predictions: int
    n_test_seasons: int
    sign_accuracy: float
    pair_sign_accuracy: float
    n_pairs: int
    pearson_r: float
    mae: float
    rmse: float
    baseline_mae: float
    skill_score: float
    predictions: pd.DataFrame


def backtest_ratings(
    gaps: pd.DataFrame,
    *,
    min_train_seasons: int = 5,
    prior_weight: float = 8.0,
) -> BacktestResult:
    """Expanding-window temporal backtest of the ratings' predictive power.

    For each test season ``Y`` (after the first ``min_train_seasons``), fit ratings
    on all comparisons before ``Y`` and predict ``Y``'s teammate gaps from the
    fitted deficits — scoring only pairings whose *both* drivers were rated in
    training. Metrics are pooled across all test seasons.
    """
    _check(gaps)
    seasons = sorted(int(s) for s in gaps["season"].unique())
    frames: list[pd.DataFrame] = []
    for year in seasons[min_train_seasons:]:
        train = gaps[gaps["season"] < year]
        test = _dedupe_undirected(gaps[gaps["season"] == year]).copy()
        if train.empty or test.empty:
            continue
        deficit = compute_ratings(train, prior_weight=prior_weight).ratings.set_index("driver_id")[
            "pace_deficit"
        ]
        test["predicted"] = test["driver_id"].map(deficit) - test["teammate_id"].map(deficit)
        test = test.dropna(subset=["predicted"])
        if not test.empty:
            frames.append(
                test[["season", "driver_id", "teammate_id", "predicted"]].assign(
                    actual=test["pace_gap"].to_numpy()
                )
            )

    predictions = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(columns=["season", "driver_id", "teammate_id", "predicted", "actual"])
    )
    if predictions.empty:
        nan = float("nan")
        return BacktestResult(0, 0, nan, nan, 0, nan, nan, nan, nan, nan, predictions)

    def _sign_acc(pred: np.ndarray, act: np.ndarray) -> float:
        nz = act != 0
        return float(np.mean(np.sign(pred[nz]) == np.sign(act[nz]))) if nz.any() else float("nan")

    pred = predictions["predicted"].to_numpy(dtype=float)
    act = predictions["actual"].to_numpy(dtype=float)
    sign_accuracy = _sign_acc(pred, act)

    # Season-pair level: average the races of each teammate pair within a test
    # season into one prediction — "who won the season-long quali battle" — which
    # is far less noisy than a single session.
    pairs = predictions.groupby(["season", "driver_id", "teammate_id"], as_index=False).agg(
        predicted=("predicted", "mean"), actual=("actual", "mean")
    )
    pair_sign_accuracy = _sign_acc(
        pairs["predicted"].to_numpy(dtype=float), pairs["actual"].to_numpy(dtype=float)
    )
    pearson_r = float(np.corrcoef(pred, act)[0, 1]) if len(pred) > 1 else float("nan")
    mae = float(np.mean(np.abs(pred - act)))
    rmse = float(np.sqrt(np.mean((pred - act) ** 2)))
    baseline_mae = float(np.mean(np.abs(act)))  # naive predictor: gap = 0
    skill_score = 1.0 - mae / baseline_mae if baseline_mae > 0 else float("nan")

    log.info(
        "ratings.backtest",
        n_predictions=len(pred),
        sign_accuracy=round(sign_accuracy, 4),
        pair_sign_accuracy=round(pair_sign_accuracy, 4),
        pearson_r=round(pearson_r, 4),
        skill_score=round(skill_score, 4),
    )
    return BacktestResult(
        n_predictions=len(pred),
        n_test_seasons=int(predictions["season"].nunique()),
        sign_accuracy=sign_accuracy,
        pair_sign_accuracy=pair_sign_accuracy,
        n_pairs=len(pairs),
        pearson_r=pearson_r,
        mae=mae,
        rmse=rmse,
        baseline_mae=baseline_mae,
        skill_score=skill_score,
        predictions=predictions,
    )


def bootstrap_ratings(
    gaps: pd.DataFrame,
    *,
    n_boot: int = 300,
    prior_weight: float = 8.0,
    seed: int = 0,
    ci: float = 0.90,
    min_presence: float = 0.5,
) -> pd.DataFrame:
    """Percentile confidence intervals per driver by resampling comparisons.

    Resamples the undirected comparison edges with replacement ``n_boot`` times,
    refits, and reports the ``ci`` percentile band of each driver's rating.
    Drivers appearing in fewer than ``min_presence`` of the resamples (edges that
    isolate them from the main component) are dropped. Deterministic given ``seed``.
    """
    _check(gaps)
    base = compute_ratings(gaps, prior_weight=prior_weight).ratings.set_index("driver_id")["rating"]
    undirected = _dedupe_undirected(gaps).reset_index(drop=True)
    n_edges = len(undirected)
    rng = np.random.default_rng(seed)
    collected: dict[str, list[float]] = {d: [] for d in base.index}

    for _ in range(n_boot):
        take = rng.integers(0, n_edges, size=n_edges)
        directed = _make_directed(undirected.iloc[take])
        fit = compute_ratings(directed, prior_weight=prior_weight).ratings
        for driver, rating in zip(fit["driver_id"], fit["rating"], strict=True):
            if driver in collected:
                collected[driver].append(float(rating))

    lo_q, hi_q = (1.0 - ci) / 2.0, 1.0 - (1.0 - ci) / 2.0
    rows = []
    for driver, rating in base.items():
        vals = collected[str(driver)]
        if len(vals) >= min_presence * n_boot:
            arr = np.asarray(vals, dtype=float)
            rows.append(
                {
                    "driver_id": driver,
                    "rating": float(rating),
                    "rating_lo": float(np.quantile(arr, lo_q)),
                    "rating_hi": float(np.quantile(arr, hi_q)),
                    "n_boot": len(vals),
                }
            )
    out = pd.DataFrame(rows).sort_values("rating", ascending=False, ignore_index=True)
    log.info("ratings.bootstrap", n_boot=n_boot, drivers=len(out))
    return out


def shrinkage_sensitivity(
    gaps: pd.DataFrame,
    *,
    prior_weights: tuple[float, ...] = (0.0, 2.0, 4.0, 8.0, 16.0, 32.0),
    default: float = 8.0,
    top_n: int = 20,
) -> pd.DataFrame:
    """Sweep ``prior_weight`` and report leaderboard stability vs the default.

    Returns one row per prior weight: the Spearman rank correlation against the
    default fit, the fraction of the default top-``top_n`` that stay in the top-N,
    and the mean absolute rating (which shrinks toward 0 as the prior tightens).
    """
    _check(gaps)
    fits = {
        pw: compute_ratings(gaps, prior_weight=pw).ratings.set_index("driver_id")
        for pw in prior_weights
    }
    base = fits[default]
    base_top = set(base.index[base["rank"] <= top_n])
    rows = []
    for pw in prior_weights:
        fit = fits[pw]
        common = base.index.intersection(fit.index)
        rho = _spearman(base.loc[common, "rank"], fit.loc[common, "rank"])
        overlap = len(base_top & set(fit.index[fit["rank"] <= top_n])) / float(top_n)
        rows.append(
            {
                "prior_weight": pw,
                "spearman_vs_default": rho,
                "top_n_overlap": overlap,
                "mean_abs_rating": float(fit["rating"].abs().mean()),
            }
        )
    return pd.DataFrame(rows)


@dataclass(frozen=True)
class ModelComparisonResult:
    """Out-of-sample comparison of static and time-varying ratings."""

    n_predictions: int
    static_mae: float
    dynamic_mae: float
    static_sign_accuracy: float
    dynamic_sign_accuracy: float
    predictions: pd.DataFrame


def compare_dynamic_backtest(
    gaps: pd.DataFrame,
    *,
    min_train_seasons: int = 5,
    static_prior_weight: float = 8.0,
    dynamic_prior_weight: float = 8.0,
    temporal_weight: float = 48.0,
) -> ModelComparisonResult:
    """Compare static vs latest driver-season ratings on future seasons."""
    _check(gaps)
    seasons = sorted(int(season) for season in gaps["season"].unique())
    frames: list[pd.DataFrame] = []
    for year in seasons[min_train_seasons:]:
        train = gaps[gaps["season"] < year]
        test = _dedupe_undirected(gaps[gaps["season"] == year]).copy()
        if train.empty or test.empty:
            continue
        static = compute_ratings(train, prior_weight=static_prior_weight).ratings.set_index(
            "driver_id"
        )["pace_deficit"]
        dynamic_fit = compute_dynamic_ratings(
            train,
            prior_weight=dynamic_prior_weight,
            temporal_weight=temporal_weight,
        ).ratings
        latest = (
            dynamic_fit.sort_values("season")
            .groupby("driver_id", as_index=False)
            .tail(1)
            .set_index("driver_id")["pace_deficit"]
        )
        test["static_predicted"] = test["driver_id"].map(static) - test["teammate_id"].map(static)
        test["dynamic_predicted"] = test["driver_id"].map(latest) - test["teammate_id"].map(latest)
        test = test.dropna(subset=["static_predicted", "dynamic_predicted"])
        if not test.empty:
            frames.append(
                test[
                    ["season", "driver_id", "teammate_id", "static_predicted", "dynamic_predicted"]
                ].assign(actual=test["pace_gap"].to_numpy())
            )

    predictions = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(
            columns=[
                "season",
                "driver_id",
                "teammate_id",
                "static_predicted",
                "dynamic_predicted",
                "actual",
            ]
        )
    )
    if predictions.empty:
        nan = float("nan")
        return ModelComparisonResult(0, nan, nan, nan, nan, predictions)

    actual = predictions["actual"].to_numpy(dtype=float)
    static_prediction = predictions["static_predicted"].to_numpy(dtype=float)
    dynamic_prediction = predictions["dynamic_predicted"].to_numpy(dtype=float)
    nonzero = actual != 0
    static_sign = float(np.mean(np.sign(static_prediction[nonzero]) == np.sign(actual[nonzero])))
    dynamic_sign = float(np.mean(np.sign(dynamic_prediction[nonzero]) == np.sign(actual[nonzero])))
    return ModelComparisonResult(
        n_predictions=len(predictions),
        static_mae=float(np.mean(np.abs(static_prediction - actual))),
        dynamic_mae=float(np.mean(np.abs(dynamic_prediction - actual))),
        static_sign_accuracy=static_sign,
        dynamic_sign_accuracy=dynamic_sign,
        predictions=predictions,
    )
