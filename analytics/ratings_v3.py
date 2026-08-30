"""Experimental joint qualifying/race-pace driver ratings (V3).

V3 is deliberately separate from the production V1/V2 ratings.  It fits a
driver-season deficit for each discipline and partially pools (rather than
equates) qualifying and controlled race pace.  Temporal and cross-discipline
links are ordinary quadratic penalties, which makes the objective explicit and
the solution deterministic.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import pairwise

import numpy as np
import pandas as pd

from analytics.ratings import compute_ratings, largest_component
from analytics.ratings_v2 import compute_dynamic_ratings

_REQUIRED = {"driver_id", "teammate_id", "pace_gap", "season"}
_RATING_COLUMNS = [
    "season",
    "rank",
    "driver_id",
    "rating",
    "pace_deficit",
    "quali_rating",
    "race_rating",
    "discipline_delta",
    "form_delta",
    "n_quali_comparisons",
    "n_race_comparisons",
]


@dataclass(frozen=True)
class V3Parameters:
    """Regularisation strengths considered by the time-series tuner."""

    prior_weight: float = 8.0
    temporal_weight: float = 48.0
    cross_discipline_weight: float = 16.0
    race_weight: float = 1.0

    @property
    def label(self) -> str:
        return (
            f"p={self.prior_weight:g},t={self.temporal_weight:g},"
            f"x={self.cross_discipline_weight:g},r={self.race_weight:g}"
        )


DEFAULT_CANDIDATES = (
    V3Parameters(4.0, 24.0, 8.0, 0.75),
    V3Parameters(8.0, 48.0, 16.0, 1.0),
    V3Parameters(16.0, 96.0, 32.0, 1.25),
)
DEFAULT_PARAMETERS = V3Parameters()


@dataclass(frozen=True)
class JointRatingResult:
    """Driver-season ratings and least-squares diagnostics."""

    ratings: pd.DataFrame
    residual_scale: float
    main_component_size: int


@dataclass(frozen=True)
class V3ExperimentResult:
    """Materialisable V3 outputs; none replaces the V1/V2 marts."""

    ratings: pd.DataFrame
    validation: pd.DataFrame
    ablation: pd.DataFrame
    selected_parameters: V3Parameters
    holdout_status: str
    recommended_for_promotion: bool


def _check(gaps: pd.DataFrame, name: str) -> None:
    missing = _REQUIRED - set(gaps.columns)
    if missing:
        raise ValueError(f"{name} is missing columns: {sorted(missing)}")


def _prepare(qualifying: pd.DataFrame, race: pd.DataFrame) -> pd.DataFrame:
    _check(qualifying, "qualifying")
    _check(race, "race")
    frames: list[pd.DataFrame] = []
    for source, raw in (("qualifying", qualifying), ("race", race)):
        frame = raw.copy()
        frame["discipline"] = source
        if "weight" in frame:
            weight = frame["weight"].astype(float)
        elif source == "qualifying" and "common_session" in frame:
            weight = frame["common_session"].map({"Q1": 0.8, "Q2": 0.9, "Q3": 1.0}).fillna(0.8)
        elif source == "race" and "n_laps" in frame:
            positive = frame.loc[frame["n_laps"].astype(float) > 0, "n_laps"].astype(float)
            median = float(positive.median()) if not positive.empty else 1.0
            weight = (frame["n_laps"].astype(float) / median).clip(0.5, 2.0)
        else:
            weight = pd.Series(1.0, index=frame.index)
        frame["observation_weight"] = weight.astype(float)
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True)
    combined["driver_id"] = combined["driver_id"].astype(str)
    combined["teammate_id"] = combined["teammate_id"].astype(str)
    combined["season"] = combined["season"].astype(int)
    combined["pace_gap"] = combined["pace_gap"].astype(float)
    finite = np.isfinite(combined["pace_gap"]) & np.isfinite(combined["observation_weight"])
    if not finite.all() or (combined["observation_weight"] <= 0).any():
        raise ValueError(
            "pace gaps and observation weights must be finite; weights must be positive"
        )
    return combined


def fit_joint_ratings(
    qualifying: pd.DataFrame,
    race: pd.DataFrame,
    *,
    parameters: V3Parameters = DEFAULT_PARAMETERS,
) -> JointRatingResult:
    """Solve the joint regularised least-squares objective.

    Observation equations model teammate gaps within a discipline.  Ridge
    penalties anchor sparse nodes, temporal edges share information between a
    driver's adjacent seasons, and cross-discipline edges partially pool the
    two estimates in the same season.
    """
    for value in asdict(parameters).values():
        if float(value) < 0:
            raise ValueError("V3 weights must be non-negative")
    frame = _prepare(qualifying, race)
    if frame.empty:
        return JointRatingResult(pd.DataFrame(columns=_RATING_COLUMNS), float("nan"), 0)

    main = largest_component(frame)
    frame = frame[frame["driver_id"].isin(main) & frame["teammate_id"].isin(main)].copy()
    nodes = sorted(
        set(zip(frame["driver_id"], frame["season"], frame["discipline"], strict=True))
        | set(zip(frame["teammate_id"], frame["season"], frame["discipline"], strict=True))
    )
    index = {node: i for i, node in enumerate(nodes)}
    equations: list[np.ndarray] = []
    targets: list[float] = []

    def add_equation(left: int, right: int | None, target: float, weight: float) -> None:
        if weight <= 0:
            return
        row = np.zeros(len(nodes), dtype=float)
        scale = float(np.sqrt(weight))
        row[left] = scale
        if right is not None:
            row[right] = -scale
        equations.append(row)
        targets.append(target * scale)

    for row in frame.itertuples():
        discipline_weight = parameters.race_weight if row.discipline == "race" else 1.0
        add_equation(
            index[(row.driver_id, int(row.season), row.discipline)],
            index[(row.teammate_id, int(row.season), row.discipline)],
            float(row.pace_gap),
            float(row.observation_weight) * discipline_weight,
        )
    for node_index in range(len(nodes)):
        add_equation(node_index, None, 0.0, parameters.prior_weight)

    by_driver_discipline: dict[tuple[str, str], list[int]] = {}
    available = set(nodes)
    for driver, season, discipline in nodes:
        by_driver_discipline.setdefault((driver, discipline), []).append(season)
        other = "race" if discipline == "qualifying" else "qualifying"
        if discipline == "qualifying" and (driver, season, other) in available:
            add_equation(
                index[(driver, season, discipline)],
                index[(driver, season, other)],
                0.0,
                parameters.cross_discipline_weight,
            )
    for (driver, discipline), seasons in by_driver_discipline.items():
        for previous, current in pairwise(sorted(seasons)):
            add_equation(
                index[(driver, current, discipline)],
                index[(driver, previous, discipline)],
                0.0,
                parameters.temporal_weight / (current - previous),
            )

    design = np.vstack(equations)
    target = np.asarray(targets, dtype=float)
    deficit, _, _, _ = np.linalg.lstsq(design, target, rcond=None)
    observation_count = len(frame)
    residual = design[:observation_count] @ deficit - target[:observation_count]
    residual_scale = float(np.sqrt(np.mean(residual**2))) if observation_count else float("nan")

    node_frame = pd.DataFrame(
        {
            "driver_id": [node[0] for node in nodes],
            "season": [node[1] for node in nodes],
            "discipline": [node[2] for node in nodes],
            "pace_deficit": deficit,
        }
    )
    wide = node_frame.pivot(
        index=["driver_id", "season"], columns="discipline", values="pace_deficit"
    )
    wide = wide.rename(
        columns={"qualifying": "quali_deficit", "race": "race_deficit"}
    ).reset_index()
    for column in ("quali_deficit", "race_deficit"):
        if column not in wide:
            wide[column] = np.nan
    available_count = wide[["quali_deficit", "race_deficit"]].notna().sum(axis=1)
    wide["pace_deficit"] = wide[["quali_deficit", "race_deficit"]].sum(axis=1) / available_count
    wide["rating"] = -wide["pace_deficit"]
    wide["quali_rating"] = -wide["quali_deficit"]
    wide["race_rating"] = -wide["race_deficit"]
    wide["discipline_delta"] = wide["race_rating"] - wide["quali_rating"]
    counts = frame.groupby(["driver_id", "season", "discipline"]).size().unstack(fill_value=0)
    for discipline in ("qualifying", "race"):
        if discipline not in counts:
            counts[discipline] = 0
    counts = counts.rename(
        columns={
            "qualifying": "n_quali_comparisons",
            "race": "n_race_comparisons",
        }
    ).reset_index()
    ratings = wide.merge(counts, on=["driver_id", "season"], how="left")
    ratings["rank"] = (
        ratings.groupby("season")["rating"].rank(method="first", ascending=False).astype(int)
    )
    ratings = ratings.sort_values(["driver_id", "season"], ignore_index=True)
    ratings["form_delta"] = ratings.groupby("driver_id")["rating"].diff()
    ratings = ratings.loc[:, _RATING_COLUMNS].sort_values(["season", "rank"], ignore_index=True)
    return JointRatingResult(ratings, residual_scale, len(main))


def bootstrap_joint_intervals(
    qualifying: pd.DataFrame,
    race: pd.DataFrame,
    *,
    parameters: V3Parameters = DEFAULT_PARAMETERS,
    n_boot: int = 100,
    seed: int = 0,
    interval: float = 0.90,
) -> pd.DataFrame:
    """Cluster-bootstrap joint ratings by whole race weekends."""
    if n_boot <= 0:
        raise ValueError("n_boot must be positive")
    if not 0 < interval < 1:
        raise ValueError("interval must be in (0, 1)")
    base = fit_joint_ratings(qualifying, race, parameters=parameters).ratings
    if base.empty:
        return pd.DataFrame(columns=["driver_id", "season", "rating_lo", "rating_hi", "n_boot"])
    rng = np.random.default_rng(seed)
    collected: dict[tuple[str, int], list[float]] = {
        (str(row.driver_id), int(row.season)): [] for row in base.itertuples()
    }

    def with_cluster(frame: pd.DataFrame) -> pd.DataFrame:
        clustered = frame.copy()
        clustered["__cluster"] = (
            clustered["race_key"].astype(str)
            if "race_key" in clustered
            else clustered["season"].astype(str)
        )
        return clustered

    clustered_q, clustered_r = with_cluster(qualifying), with_cluster(race)

    def sample_pair() -> tuple[pd.DataFrame, pd.DataFrame]:
        """Use the same weekend draw in both disciplines to preserve correlation."""
        q_chunks: list[pd.DataFrame] = []
        r_chunks: list[pd.DataFrame] = []
        seasons = sorted(
            set(clustered_q["season"].astype(int)) | set(clustered_r["season"].astype(int))
        )
        for season in seasons:
            season_q = clustered_q[clustered_q["season"] == season]
            season_r = clustered_r[clustered_r["season"] == season]
            clusters = pd.concat([season_q["__cluster"], season_r["__cluster"]]).drop_duplicates()
            selected = rng.choice(clusters.to_numpy(), size=len(clusters), replace=True)
            q_chunks.extend(season_q[season_q["__cluster"] == key] for key in selected)
            r_chunks.extend(season_r[season_r["__cluster"] == key] for key in selected)

        def combine(chunks: list[pd.DataFrame], original: pd.DataFrame) -> pd.DataFrame:
            sampled = pd.concat(chunks, ignore_index=True) if chunks else original.iloc[0:0].copy()
            return sampled.drop(columns="__cluster")

        return combine(q_chunks, clustered_q), combine(r_chunks, clustered_r)

    for _ in range(n_boot):
        sampled_q, sampled_r = sample_pair()
        fitted = fit_joint_ratings(sampled_q, sampled_r, parameters=parameters).ratings
        for row in fitted.itertuples():
            key = (str(row.driver_id), int(row.season))
            if key in collected:
                collected[key].append(float(row.rating))
    base_rating = base.set_index(["driver_id", "season"])["rating"]
    alpha = (1.0 - interval) / 2.0
    rows: list[dict[str, object]] = []
    for key, samples in collected.items():
        if len(samples) < n_boot / 2:
            continue
        point = float(base_rating.loc[key])
        rows.append(
            {
                "driver_id": key[0],
                "season": key[1],
                "rating_lo": min(point, float(np.quantile(samples, alpha))),
                "rating_hi": max(point, float(np.quantile(samples, 1.0 - alpha))),
                "n_boot": len(samples),
            }
        )
    return pd.DataFrame(rows)


def _undirected(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame["driver_id"].astype(str) < frame["teammate_id"].astype(str)].copy()


def _latest_deficits(ratings: pd.DataFrame, discipline: str) -> pd.Series:
    column = "quali_rating" if discipline == "qualifying" else "race_rating"
    latest = ratings.dropna(subset=[column]).sort_values("season").groupby("driver_id").tail(1)
    return -latest.set_index("driver_id")[column]


def _predict_joint(
    qualifying_train: pd.DataFrame,
    race_train: pd.DataFrame,
    qualifying_test: pd.DataFrame,
    race_test: pd.DataFrame,
    parameters: V3Parameters,
) -> pd.DataFrame:
    fit = fit_joint_ratings(qualifying_train, race_train, parameters=parameters)
    frames: list[pd.DataFrame] = []
    for discipline, raw in (("qualifying", qualifying_test), ("race", race_test)):
        test = _undirected(raw)
        if test.empty:
            continue
        deficit = _latest_deficits(fit.ratings, discipline)
        test["predicted"] = test["driver_id"].map(deficit) - test["teammate_id"].map(deficit)
        test = test.dropna(subset=["predicted"])
        if not test.empty:
            frames.append(
                test[["season", "driver_id", "teammate_id", "predicted"]].assign(
                    actual=test["pace_gap"].to_numpy(), discipline=discipline
                )
            )
    return (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(
            columns=["season", "driver_id", "teammate_id", "predicted", "actual", "discipline"]
        )
    )


def _walk_forward(
    qualifying: pd.DataFrame,
    race: pd.DataFrame,
    parameters: V3Parameters,
    *,
    min_train_seasons: int,
    excluded_season: int | None = None,
) -> pd.DataFrame:
    seasons = sorted(set(qualifying["season"].astype(int)) | set(race["season"].astype(int)))
    if excluded_season is not None:
        seasons = [season for season in seasons if season != excluded_season]
    frames: list[pd.DataFrame] = []
    for year in seasons[min_train_seasons:]:
        predicted = _predict_joint(
            qualifying[qualifying["season"] < year],
            race[race["season"] < year],
            qualifying[qualifying["season"] == year],
            race[race["season"] == year],
            parameters,
        )
        if not predicted.empty:
            frames.append(predicted)
    return (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(
            columns=["season", "driver_id", "teammate_id", "predicted", "actual", "discipline"]
        )
    )


def _choose_parameters(
    qualifying: pd.DataFrame,
    race: pd.DataFrame,
    candidates: tuple[V3Parameters, ...],
    min_train_seasons: int,
) -> tuple[V3Parameters, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    for order, candidate in enumerate(candidates):
        predictions = _walk_forward(
            qualifying,
            race,
            candidate,
            min_train_seasons=min_train_seasons,
        )
        mae = (
            float((predictions["predicted"] - predictions["actual"]).abs().mean())
            if not predictions.empty
            else float("inf")
        )
        rows.append(
            {"order": order, "parameters": candidate, "inner_mae": mae, "n": len(predictions)}
        )
    scores = pd.DataFrame(rows).sort_values(["inner_mae", "order"], ignore_index=True)
    return scores.iloc[0]["parameters"], scores


def _metrics(predictions: pd.DataFrame, model: str, split: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for discipline, frame in [("combined", predictions), *list(predictions.groupby("discipline"))]:
        if frame.empty:
            continue
        error = frame["predicted"].to_numpy(float) - frame["actual"].to_numpy(float)
        actual = frame["actual"].to_numpy(float)
        nonzero = actual != 0
        rows.append(
            {
                "split": split,
                "model": model,
                "discipline": discipline,
                "n_predictions": len(frame),
                "mae": float(np.mean(np.abs(error))),
                "rmse": float(np.sqrt(np.mean(error**2))),
                "direction_accuracy": (
                    float(
                        np.mean(
                            np.sign(frame.loc[nonzero, "predicted"]) == np.sign(actual[nonzero])
                        )
                    )
                    if nonzero.any()
                    else float("nan")
                ),
                "interval_coverage": (
                    float(
                        np.mean(
                            (frame["actual"] >= frame["interval_lo"])
                            & (frame["actual"] <= frame["interval_hi"])
                        )
                    )
                    if "interval_lo" in frame
                    else float("nan")
                ),
                "mean_interval_width": (
                    float((frame["interval_hi"] - frame["interval_lo"]).mean())
                    if "interval_lo" in frame
                    else float("nan")
                ),
            }
        )
    return rows


def _add_calibrated_interval(
    predictions: pd.DataFrame, calibration: pd.DataFrame, interval: float
) -> pd.DataFrame:
    result = predictions.copy()
    if result.empty:
        result["interval_lo"] = pd.Series(dtype=float)
        result["interval_hi"] = pd.Series(dtype=float)
        return result
    errors = (calibration["predicted"] - calibration["actual"]).abs()
    radius = float(errors.quantile(interval)) if not errors.empty else float("nan")
    result["interval_lo"] = result["predicted"] - radius
    result["interval_hi"] = result["predicted"] + radius
    return result


def _predict_baseline(
    qualifying_train: pd.DataFrame,
    race_train: pd.DataFrame,
    qualifying_test: pd.DataFrame,
    race_test: pd.DataFrame,
    *,
    dynamic: bool,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for discipline, train, raw_test in (
        ("qualifying", qualifying_train, qualifying_test),
        ("race", race_train, race_test),
    ):
        test = _undirected(raw_test)
        if train.empty or test.empty:
            continue
        if dynamic:
            fitted = compute_dynamic_ratings(train).ratings
            deficit = (
                fitted.sort_values("season")
                .groupby("driver_id")
                .tail(1)
                .set_index("driver_id")["pace_deficit"]
            )
        else:
            deficit = compute_ratings(train).ratings.set_index("driver_id")["pace_deficit"]
        test["predicted"] = test["driver_id"].map(deficit) - test["teammate_id"].map(deficit)
        test = test.dropna(subset=["predicted"])
        frames.append(
            test[["season", "driver_id", "teammate_id", "predicted"]].assign(
                actual=test["pace_gap"].to_numpy(), discipline=discipline
            )
        )
    return (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(
            columns=["season", "driver_id", "teammate_id", "predicted", "actual", "discipline"]
        )
    )


def evaluate_v3_experiment(
    qualifying: pd.DataFrame,
    race: pd.DataFrame,
    *,
    final_holdout_season: int = 2026,
    min_train_seasons: int = 3,
    candidates: tuple[V3Parameters, ...] = DEFAULT_CANDIDATES,
    interval: float = 0.90,
    n_boot: int = 100,
    seed: int = 0,
) -> V3ExperimentResult:
    """Run nested temporal validation and an explicitly untouched final holdout."""
    if not candidates:
        raise ValueError("at least one V3 parameter candidate is required")
    _check(qualifying, "qualifying")
    _check(race, "race")
    pre_q = qualifying[qualifying["season"] < final_holdout_season].copy()
    pre_r = race[race["season"] < final_holdout_season].copy()
    selected, tuning = _choose_parameters(pre_q, pre_r, candidates, min_train_seasons)

    # Nested outer folds: every fold tunes using only the fold's past.
    seasons = sorted(set(pre_q["season"].astype(int)) | set(pre_r["season"].astype(int)))
    nested_frames: list[pd.DataFrame] = []
    selections: list[str] = []
    for year in seasons[min_train_seasons:]:
        train_q, train_r = pre_q[pre_q["season"] < year], pre_r[pre_r["season"] < year]
        inner_min = min(2, max(1, len(set(train_q["season"]) | set(train_r["season"])) - 1))
        fold_parameters, _ = _choose_parameters(train_q, train_r, candidates, inner_min)
        calibration = _walk_forward(train_q, train_r, fold_parameters, min_train_seasons=inner_min)
        fold = _predict_joint(
            train_q,
            train_r,
            pre_q[pre_q["season"] == year],
            pre_r[pre_r["season"] == year],
            fold_parameters,
        )
        if not fold.empty:
            nested_frames.append(_add_calibrated_interval(fold, calibration, interval))
            selections.append(fold_parameters.label)
    nested = pd.concat(nested_frames, ignore_index=True) if nested_frames else pd.DataFrame()
    validation_rows = _metrics(nested, "v3_nested_tuned", "nested_validation")
    for row in validation_rows:
        row["status"] = "evaluated"
        row["selected_parameters"] = ";".join(selections)

    holdout_q = qualifying[qualifying["season"] == final_holdout_season]
    holdout_r = race[race["season"] == final_holdout_season]
    calibration = _walk_forward(pre_q, pre_r, selected, min_train_seasons=min_train_seasons)
    holdout = _predict_joint(pre_q, pre_r, holdout_q, holdout_r, selected)
    holdout_status = "evaluated" if not holdout.empty else "not_available"
    if not holdout.empty:
        holdout = _add_calibrated_interval(holdout, calibration, interval)
        rows = _metrics(holdout, "v3_tuned", f"final_holdout_{final_holdout_season}")
        for row in rows:
            row["status"] = "evaluated"
            row["selected_parameters"] = selected.label
        validation_rows.extend(rows)
    else:
        validation_rows.append(
            {
                "split": f"final_holdout_{final_holdout_season}",
                "model": "v3_tuned",
                "discipline": "combined",
                "n_predictions": 0,
                "mae": float("nan"),
                "rmse": float("nan"),
                "direction_accuracy": float("nan"),
                "interval_coverage": float("nan"),
                "mean_interval_width": float("nan"),
                "status": "not_available",
                "selected_parameters": selected.label,
            }
        )

    evaluation_split = (
        f"final_holdout_{final_holdout_season}" if not holdout.empty else "nested_validation"
    )
    target_q, target_r = (holdout_q, holdout_r) if not holdout.empty else (pre_q, pre_r)
    ablation_rows: list[dict[str, object]] = []
    if not holdout.empty:
        prediction_sets = {
            "static_v1_by_discipline": _predict_baseline(
                pre_q, pre_r, target_q, target_r, dynamic=False
            ),
            "dynamic_v2_by_discipline": _predict_baseline(
                pre_q, pre_r, target_q, target_r, dynamic=True
            ),
            "v3_no_cross_pooling": _predict_joint(
                pre_q,
                pre_r,
                target_q,
                target_r,
                V3Parameters(
                    selected.prior_weight, selected.temporal_weight, 0.0, selected.race_weight
                ),
            ),
            "v3_no_temporal_pooling": _predict_joint(
                pre_q,
                pre_r,
                target_q,
                target_r,
                V3Parameters(
                    selected.prior_weight,
                    0.0,
                    selected.cross_discipline_weight,
                    selected.race_weight,
                ),
            ),
            "v3_tuned": holdout,
        }
    else:
        prediction_sets = {
            "static_v1_by_discipline": pd.concat(
                [
                    _predict_baseline(
                        pre_q[pre_q["season"] < year],
                        pre_r[pre_r["season"] < year],
                        pre_q[pre_q["season"] == year],
                        pre_r[pre_r["season"] == year],
                        dynamic=False,
                    )
                    for year in seasons[min_train_seasons:]
                ],
                ignore_index=True,
            )
            if len(seasons) > min_train_seasons
            else pd.DataFrame(),
            "dynamic_v2_by_discipline": pd.concat(
                [
                    _predict_baseline(
                        pre_q[pre_q["season"] < year],
                        pre_r[pre_r["season"] < year],
                        pre_q[pre_q["season"] == year],
                        pre_r[pre_r["season"] == year],
                        dynamic=True,
                    )
                    for year in seasons[min_train_seasons:]
                ],
                ignore_index=True,
            )
            if len(seasons) > min_train_seasons
            else pd.DataFrame(),
            "v3_no_cross_pooling": _walk_forward(
                pre_q,
                pre_r,
                V3Parameters(
                    selected.prior_weight, selected.temporal_weight, 0.0, selected.race_weight
                ),
                min_train_seasons=min_train_seasons,
            ),
            "v3_no_temporal_pooling": _walk_forward(
                pre_q,
                pre_r,
                V3Parameters(
                    selected.prior_weight,
                    0.0,
                    selected.cross_discipline_weight,
                    selected.race_weight,
                ),
                min_train_seasons=min_train_seasons,
            ),
            "v3_nested_tuned": nested,
        }
    for model, predictions in prediction_sets.items():
        ablation_rows.extend(_metrics(predictions, model, evaluation_split))
    ablation = pd.DataFrame(ablation_rows)
    combined = ablation[ablation["discipline"] == "combined"].set_index("model")
    tuned_name = "v3_tuned" if not holdout.empty else "v3_nested_tuned"
    baselines = combined.loc[
        combined.index.intersection(["static_v1_by_discipline", "dynamic_v2_by_discipline"])
    ]
    recommended = bool(
        not holdout.empty
        and tuned_name in combined.index
        and not baselines.empty
        and float(combined.loc[tuned_name, "mae"]) < float(baselines["mae"].min())
        and float(combined.loc[tuned_name, "direction_accuracy"])
        >= float(baselines["direction_accuracy"].max())
    )

    full_fit = fit_joint_ratings(qualifying, race, parameters=selected).ratings
    intervals = bootstrap_joint_intervals(
        qualifying, race, parameters=selected, n_boot=n_boot, seed=seed, interval=interval
    )
    ratings = full_fit.merge(intervals, on=["driver_id", "season"], how="left")
    validation = pd.DataFrame(validation_rows)
    validation["tuning_candidates"] = len(tuning)
    validation["holdout_season"] = final_holdout_season
    validation["recommended_for_promotion"] = recommended
    return V3ExperimentResult(ratings, validation, ablation, selected, holdout_status, recommended)
