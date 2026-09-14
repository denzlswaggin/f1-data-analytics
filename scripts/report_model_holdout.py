"""Read-only temporal diagnostic, not independent race or causal validation.

Refit OLS or the production Theil-Sen fitting kernel on the first eight qualifying stint laps,
then evaluate all later qualifying laps (at least three). Existing production
fits and residuals are never inputs. Peer references remain contemporaneous;
this is not a deployable pre-race forecast or a counterfactual pit-time test.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from analytics.pit_timing import _fit

KEYS = ["season", "round", "driver_code", "stint"]
REQUIRED = [
    *KEYS,
    "lap_number",
    "tyre_life",
    "controlled_pace_delta_sec",
    "air_state",
    "replay_coverage_pct",
]


def evaluate(laps: pd.DataFrame, *, estimator: str = "ols") -> dict[str, Any]:
    """Return lap-weighted errors and auditable per-stint chronological splits."""
    if estimator not in {"ols", "production_theil_sen"}:
        raise ValueError("Unknown estimator")
    missing = set(REQUIRED) - set(laps.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    if laps[[*KEYS, "lap_number"]].isna().any().any():
        raise ValueError("Missing stint or lap identifiers")
    if laps.duplicated([*KEYS, "lap_number"]).any():
        raise ValueError("Duplicate driver-stint laps")
    data = laps[REQUIRED].copy().reset_index(drop=True)
    numeric = ["lap_number", "tyre_life", "controlled_pace_delta_sec", "replay_coverage_pct"]
    for column in numeric:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    finite = np.isfinite(data[numeric].to_numpy(dtype=float)).all(axis=1)
    eligible = (
        finite
        & data.air_state.eq("clean_air")
        & data.replay_coverage_pct.between(80, 100)
        & data.tyre_life.ge(0)
        & data.lap_number.gt(0)
    )
    selected = data.loc[eligible]
    failures: Counter[str] = Counter()
    records: list[dict[str, Any]] = []
    model_errors: list[float] = []
    baseline_errors: list[float] = []
    for key, group in data.groupby(KEYS, sort=True):
        clean = selected.loc[group.index.intersection(selected.index)].sort_values("lap_number")
        if len(clean) < 11:
            failures["fewer_than_8_train_plus_3_holdout_laps"] += 1
            continue
        train, holdout = clean.iloc[:8], clean.iloc[8:]
        x = train.tyre_life.to_numpy(dtype=float)
        y = train.controlled_pace_delta_sec.to_numpy(dtype=float)
        if np.unique(x).size < 4 or np.ptp(x) < 4:
            failures["insufficient_training_tyre_age_variation"] += 1
            continue
        # Centring improves conditioning; neither holdout values nor ages enter fit.
        centre = float(x.mean())
        if estimator == "production_theil_sen":
            slope, intercept, _ = _fit(x - centre, y)
            coefficients = np.array([intercept, slope])
        else:
            design = np.column_stack([np.ones(len(x)), x - centre])
            coefficients = np.linalg.lstsq(design, y, rcond=None)[0]
        prediction = coefficients[0] + coefficients[1] * (holdout.tyre_life.to_numpy() - centre)
        truth = holdout.controlled_pace_delta_sec.to_numpy(dtype=float)
        baseline = float(np.median(y))
        errors = np.abs(prediction - truth)
        naive_errors = np.abs(baseline - truth)
        if not np.isfinite(np.concatenate([coefficients, errors, naive_errors])).all():
            failures["nonfinite_fit_or_error"] += 1
            continue
        model_errors.extend(errors.tolist())
        baseline_errors.extend(naive_errors.tolist())
        records.append(
            {
                **{
                    name: str(value) if name == "driver_code" else int(value)
                    for name, value in zip(KEYS, key, strict=True)
                },
                "train_laps": train.lap_number.astype(int).tolist(),
                "holdout_laps": holdout.lap_number.astype(int).tolist(),
                "train_centre_tyre_age": centre,
                "intercept_at_train_centre_sec": float(coefficients[0]),
                "slope_sec_per_tyre_lap": float(coefficients[1]),
                "train_median_baseline_sec": baseline,
                "model_mae_sec": float(errors.mean()),
                "baseline_mae_sec": float(naive_errors.mean()),
            }
        )
    return {
        "protocol": "first-8-clean-laps-train_remaining-minimum-3-holdout-v1",
        "estimator": estimator,
        "input_laps": len(data),
        "qualifying_laps": len(selected),
        "excluded_input_laps": len(data) - len(selected),
        "candidate_stints": data.groupby(KEYS).ngroups,
        "evaluated_stints": len(records),
        "training_laps": 8 * len(records),
        "holdout_laps": len(model_errors),
        "model_mae_sec": float(np.mean(model_errors)) if model_errors else None,
        "baseline_mae_sec": float(np.mean(baseline_errors)) if baseline_errors else None,
        "failures": dict(sorted(failures.items())),
        "stints": records,
        "limitations": (
            "Retrospective within-stint temporal diagnostic on previously inspected races, "
            "not an unseen-race validation. The selected fitting kernel is refitted under this "
            "diagnostic's eligibility/split rules, not the complete production strategy model. "
            "Eligibility and peer references use contemporaneous observed "
            "data. No causal driver-pace, calibrated interval, or counterfactual pit accuracy claim."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=Path("data/dashboard/latest.duckdb"))
    parser.add_argument("--estimator", choices=["ols", "production_theil_sen"], default="ols")
    args = parser.parse_args()
    snapshot_hash = hashlib.sha256(args.snapshot.read_bytes()).hexdigest()
    with duckdb.connect(str(args.snapshot), read_only=True) as connection:
        laps = connection.execute("select * from marts.traffic_adjusted_laps").fetchdf()
        metadata = connection.execute(
            "select version, generated_at from dashboard.snapshot_metadata"
        ).fetchall()
    result = evaluate(laps, estimator=args.estimator)
    result["snapshot_metadata"] = metadata
    if hashlib.sha256(args.snapshot.read_bytes()).hexdigest() != snapshot_hash:
        raise ValueError("Snapshot changed during evaluation")
    result["snapshot_sha256"] = snapshot_hash
    result["implementation_sha256"] = {
        str(path): hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
        for path in (Path("scripts/report_model_holdout.py"), Path("analytics/pit_timing.py"))
    }
    print(json.dumps(result, indent=2, allow_nan=False, default=str))


if __name__ == "__main__":
    main()
