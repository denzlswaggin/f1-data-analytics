import json

import numpy as np
import pandas as pd
import pytest
from scripts.report_model_holdout import evaluate


def fixture() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "season": [2025] * 14,
            "round": [1] * 14,
            "driver_code": ["AAA"] * 14,
            "stint": [1] * 14,
            "lap_number": np.arange(1, 15),
            "tyre_life": np.arange(1, 15),
            "controlled_pace_delta_sec": np.arange(1, 15) * 0.2,
            "air_state": ["clean_air"] * 14,
            "replay_coverage_pct": [100] * 14,
        }
    )


def test_linear_split_and_baseline() -> None:
    result = evaluate(fixture())
    record = result["stints"][0]
    assert record["train_laps"] == list(range(1, 9))
    assert record["holdout_laps"] == list(range(9, 15))
    assert set(record["train_laps"]).isdisjoint(record["holdout_laps"])
    assert result["model_mae_sec"] == pytest.approx(0, abs=1e-12)
    assert result["baseline_mae_sec"] > 0


def test_holdout_values_do_not_change_fit() -> None:
    laps = fixture()
    before = evaluate(laps)["stints"][0]
    laps.loc[8:, "controlled_pace_delta_sec"] += 100
    after = evaluate(laps)["stints"][0]
    for field in (
        "slope_sec_per_tyre_lap",
        "intercept_at_train_centre_sec",
        "train_median_baseline_sec",
    ):
        assert before[field] == after[field]
    assert after["model_mae_sec"] == pytest.approx(100)


def test_empty_and_insufficient() -> None:
    assert evaluate(fixture().iloc[:0])["model_mae_sec"] is None
    result = evaluate(fixture().iloc[:10])
    assert result["evaluated_stints"] == 0
    assert result["failures"] == {"fewer_than_8_train_plus_3_holdout_laps": 1}


def test_nonfinite_and_nonclean_excluded() -> None:
    laps = fixture()
    laps.loc[0, "controlled_pace_delta_sec"] = np.inf
    laps.loc[1, "air_state"] = "traffic"
    laps.loc[2, "replay_coverage_pct"] = np.nan
    result = evaluate(laps)
    assert result["excluded_input_laps"] == 3
    assert result["training_laps"] == 8
    assert result["holdout_laps"] == 3


def test_order_and_unused_production_fit_do_not_matter() -> None:
    laps = fixture()
    laps["pace_residual_sec"] = 999
    assert evaluate(laps.sample(frac=1, random_state=9)) == evaluate(fixture())


def test_duplicate_or_missing_identifier_rejected() -> None:
    laps = fixture()
    with pytest.raises(ValueError, match="Duplicate"):
        evaluate(pd.concat([laps, laps.iloc[:1]]))
    laps.loc[0, "stint"] = np.nan
    with pytest.raises(ValueError, match="Missing stint"):
        evaluate(laps)


def test_degenerate_training_ages_not_rescued_by_holdout() -> None:
    laps = fixture()
    laps.loc[:7, "tyre_life"] = 1
    assert evaluate(laps)["failures"] == {"insufficient_training_tyre_age_variation": 1}


def test_repeated_dataframe_index_does_not_mix_stints() -> None:
    first = fixture()
    second = fixture()
    second["driver_code"] = "BBB"
    second["controlled_pace_delta_sec"] += 50
    result = evaluate(pd.concat([first, second]))
    assert result["evaluated_stints"] == 2
    assert result["holdout_laps"] == 12
    assert result["model_mae_sec"] == pytest.approx(0, abs=1e-12)


def test_missing_required_column_rejected() -> None:
    with pytest.raises(ValueError, match="Missing columns"):
        evaluate(fixture().drop(columns="air_state"))


def test_database_integer_types_serialize_without_nan() -> None:
    laps = fixture().astype({"season": "int32", "round": "int32", "stint": "int32"})
    assert json.loads(json.dumps(evaluate(laps), allow_nan=False))["evaluated_stints"] == 1
