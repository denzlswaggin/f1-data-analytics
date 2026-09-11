"""Tests for the pit-timing sensitivity counterfactual."""

from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest
from analytics import pit_timing
from analytics.pipeline import (
    build_pit_timing_sensitivity,
    build_pit_timing_sensitivity_incremental,
)
from analytics.pit_timing import PIT_TIMING_COLUMNS, analyse_pit_timing_sensitivity
from ingestion.config import Settings
from ingestion.loaders.warehouse import read_query


def test_actual_additional_pit_without_stint_change_excludes_scenarios() -> None:
    laps, replay = _race()
    stops = pd.concat([_stops(), _stops().assign(pit_lap=14)], ignore_index=True)
    result = analyse_pit_timing_sensitivity(laps, replay, stops, bootstrap_samples=5)
    assert result.summary.iloc[0]["exclusion_reason"] == "additional_stop_in_window"


@pytest.mark.parametrize("other_race", [False, True])
def test_missing_race_replay_retains_stop_without_publishing_estimates(other_race: bool) -> None:
    laps, replay = _race()
    replay = replay.assign(round=2) if other_race else replay.iloc[0:0]
    result = analyse_pit_timing_sensitivity(laps, replay, _stops())
    assert len(result.summary) == 1
    assert result.summary.iloc[0]["exclusion_reason"] == "missing_race_replay"
    assert not result.summary["eligible"].any()
    assert result.summary["estimated_gain_vs_actual_sec"].isna().all()
    assert len(result.scenarios) == 7
    assert not result.scenarios["supported"].any()
    assert result.scenarios["delta_vs_actual_sec"].isna().all()


def test_pre_attached_full_context_is_preserved() -> None:
    laps, replay = _race()
    laps["is_pit_in_lap"] = laps["driver_code"].eq("A") & laps["lap_number"].eq(14)
    laps["is_pit_out_lap"] = laps["driver_code"].eq("A") & laps["lap_number"].eq(15)
    laps["is_pit_boundary"] = laps["is_pit_in_lap"] | laps["is_pit_out_lap"]
    result = analyse_pit_timing_sensitivity(laps, replay, _stops(), bootstrap_samples=5)
    assert result.summary.iloc[0]["exclusion_reason"] == "additional_stop_in_window"


def _race(
    *, warmup_scale: float = 1.0, old_slope: float = 0.20
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    replay_rows: list[dict[str, object]] = []
    drivers = ("B", "A", "C", "D", "E", "F", "G")
    warmup = {1: 4.0, 2: 3.0, 3: 2.0, 4: 1.2, 5: 0.6, 6: 0.2}
    for lap in range(1, 22):
        for order, driver in enumerate(drivers, start=1):
            target = driver == "A"
            second_stint = target and lap >= 9
            stint = 2 if second_stint else 1
            tyre_life = lap - 8 if second_stint else lap
            compound = "HARD" if second_stint else "MEDIUM"
            lap_time = 100.0
            if target and lap <= 8:
                lap_time += old_slope * tyre_life
            elif target and lap == 9:
                lap_time += 20.0
            elif target:
                offset = lap - 9
                lap_time += -1.0 + 0.05 * offset
                lap_time += warmup_scale * warmup.get(offset, 0.0)
            rows.append(
                {
                    "season": 2026,
                    "round": 1,
                    "race_name": "Test Grand Prix",
                    "driver_code": driver,
                    "driver_name": f"Driver {driver}",
                    "team": f"Team {driver}",
                    "lap_number": lap,
                    "stint": stint,
                    "compound": compound,
                    "tyre_life": tyre_life,
                    "is_fresh_tyre": True,
                    "lap_time_sec": lap_time,
                    "track_status": "1",
                }
            )
            for offset in range(100):
                replay_rows.append(
                    {
                        "season": 2026,
                        "round": 1,
                        "driver_code": driver,
                        "lap_number": lap,
                        "stint": stint,
                        "t_s": float((lap - 1) * 100 + offset),
                        "running_order": order,
                        "gap_to_ahead_s": 0.0 if order == 1 else 4.0,
                    }
                )
    return pd.DataFrame(rows), pd.DataFrame(replay_rows)


def _stops(duration: float = 22.5) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "season": 2026,
                "round": 1,
                "driver_code": "A",
                "pit_lap": 8,
                "duration_sec": duration,
            }
        ]
    )


def _result(
    laps: pd.DataFrame,
    replay: pd.DataFrame,
    stops: pd.DataFrame | None = None,
) -> tuple[pd.Series, pd.DataFrame]:
    result = analyse_pit_timing_sensitivity(
        laps, replay, stops, bootstrap_samples=100, random_seed=17
    )
    summary = result.summary.loc[result.summary["driver_code"].eq("A")].iloc[0]
    scenarios = result.scenarios.loc[result.scenarios["driver_code"].eq("A")]
    return summary, scenarios


def test_models_all_seven_shifts_and_retains_compound_advantage() -> None:
    laps, replay = _race()

    summary, scenarios = _result(laps, replay, _stops())

    assert summary["eligible"]
    assert summary["supported_scenarios"] == 7
    assert set(scenarios["shift_laps"]) == set(range(-3, 4))
    assert scenarios["supported"].all()
    assert summary["best_supported_shift_laps"] < 0
    assert summary["estimated_gain_vs_actual_sec"] > 0
    assert scenarios.loc[scenarios["shift_laps"].eq(0), "delta_vs_actual_sec"].iloc[
        0
    ] == pytest.approx(0.0)


def test_shared_field_slowdown_and_driver_offset_cancel() -> None:
    laps, replay = _race()
    _, baseline = _result(laps, replay)
    changed = laps.copy()
    changed.loc[changed["lap_number"].eq(12), "lap_time_sec"] += 5.0
    _, field_slowdown = _result(changed, replay)
    offset = laps.copy()
    offset.loc[offset["driver_code"].eq("A"), "lap_time_sec"] += 2.0
    _, driver_offset = _result(offset, replay)

    expected = baseline.set_index("shift_laps")["delta_vs_actual_sec"]
    assert field_slowdown.set_index("shift_laps")[
        "delta_vs_actual_sec"
    ].to_numpy() == pytest.approx(expected.to_numpy())
    assert driver_offset.set_index("shift_laps")["delta_vs_actual_sec"].to_numpy() == pytest.approx(
        expected.to_numpy()
    )


def test_old_tyre_degradation_changes_tradeoff_and_warmup_moves_with_stop() -> None:
    low_degradation_laps, replay = _race(old_slope=0.0)
    high_degradation_laps, _ = _race(old_slope=0.35)
    low_warmup_laps, _ = _race(warmup_scale=0.2)
    high_warmup_laps, _ = _race(warmup_scale=2.0)

    _, low_deg = _result(low_degradation_laps, replay)
    _, high_deg = _result(high_degradation_laps, replay)
    _, low_warmup = _result(low_warmup_laps, replay)
    _, high_warmup = _result(high_warmup_laps, replay)

    later = 3
    low_deg_delta = low_deg.set_index("shift_laps").loc[later, "delta_vs_actual_sec"]
    high_deg_delta = high_deg.set_index("shift_laps").loc[later, "delta_vs_actual_sec"]
    assert high_deg_delta > low_deg_delta
    early = -3
    low_warmup_delta = low_warmup.set_index("shift_laps").loc[early, "delta_vs_actual_sec"]
    high_warmup_delta = high_warmup.set_index("shift_laps").loc[early, "delta_vs_actual_sec"]
    # Every scenario includes the full six-lap settling profile. Moving that
    # observed profile with the stop must not create a synthetic timing gain.
    assert high_warmup_delta == pytest.approx(low_warmup_delta)


def test_pit_duration_is_context_only() -> None:
    laps, replay = _race()
    first_summary, first = _result(laps, replay, _stops(20.0))
    second_summary, second = _result(laps, replay, _stops(35.0))

    assert first_summary["pit_duration_sec"] == 20.0
    assert second_summary["pit_duration_sec"] == 35.0
    assert first["delta_vs_actual_sec"].to_numpy() == pytest.approx(
        second["delta_vs_actual_sec"].to_numpy()
    )


def test_bootstrap_is_reproducible_and_reports_uncertainty() -> None:
    laps, replay = _race()
    first_summary, first = _result(laps, replay)
    second_summary, second = _result(laps, replay)

    assert first["delta_p25_sec"].to_numpy() == pytest.approx(second["delta_p25_sec"].to_numpy())
    assert first["delta_p75_sec"].to_numpy() == pytest.approx(second["delta_p75_sec"].to_numpy())
    assert first_summary["best_shift_win_pct"] == second_summary["best_shift_win_pct"]
    assert first_summary["bootstrap_requested_samples"] == 100
    assert first_summary["bootstrap_valid_samples"] == 100
    assert first_summary["bootstrap_attempted_samples"] >= 100


def test_small_gain_is_not_mislabelled_as_interval_containing_actual() -> None:
    laps, replay = _race()
    target = laps.driver_code.eq("A")
    laps.loc[target & laps.lap_number.lt(9), "lap_time_sec"] = 100.05
    laps.loc[target & laps.lap_number.gt(9), "lap_time_sec"] = 100.0
    summary, _ = _result(laps, replay)
    assert summary["estimated_gain_vs_actual_sec"] == pytest.approx(0.15)
    assert summary["best_delta_p75_sec"] < 0
    assert summary["timing_signal"] == "No meaningful directional signal"


def test_noisy_fixture_direction_is_stable_across_resampling_budgets() -> None:
    laps, replay = _race()
    target = laps.driver_code.eq("A")
    laps.loc[target, "lap_time_sec"] += laps.loc[target, "lap_number"].mod(3) * 0.07
    for samples in (100, 300, 600):
        summary = analyse_pit_timing_sensitivity(
            laps, replay, bootstrap_samples=samples, random_seed=17
        ).summary.iloc[0]
        assert summary["bootstrap_valid_samples"] == samples
        assert summary["best_supported_shift_laps"] == -3
        assert summary["best_delta_p25_sec"] == pytest.approx(-5.718)
        assert summary["best_delta_p75_sec"] == pytest.approx(-5.340)
        assert summary["confidence"] == "medium"
        assert "optimum unlocated" in summary["timing_signal"]


def test_extrapolation_exact_boundary_and_warmup_not_counted_as_extrapolation() -> None:
    laps, replay = _race()
    summary, scenarios = _result(laps, replay)
    by_shift = scenarios.set_index("shift_laps")
    assert by_shift.loc[3, "old_extrapolation_laps"] == 4
    assert by_shift.loc[3, "supported"]
    assert by_shift["new_extrapolation_laps"].eq(0).all()
    assert summary["actual_old_extrapolation_laps"] == 1
    assert summary["boundary_minimum"]
    assert summary["confidence"] != "high"
    assert "optimum unlocated" in summary["timing_signal"]


def test_partial_scenario_support_retains_all_rows_and_nulls_rejected_estimates() -> None:
    laps, replay = _race()
    result = analyse_pit_timing_sensitivity(
        laps, replay, bootstrap_samples=100, max_old_extrapolation_laps=2
    )
    scenarios = result.scenarios.set_index("shift_laps")
    assert result.summary.iloc[0]["supported_scenarios"] == 5
    assert scenarios.loc[1, "supported"]
    assert not scenarios.loc[2, "supported"]
    assert scenarios.loc[2, "old_extrapolation_laps"] == 3
    assert scenarios.loc[2, "exclusion_reason"] == "old_reference_extrapolation_limit"
    assert (
        scenarios.loc[[2, 3], ["delta_vs_actual_sec", "delta_p25_sec", "estimated_cost_index_sec"]]
        .isna()
        .all()
        .all()
    )


def test_sparse_new_references_gate_earlier_extrapolation() -> None:
    laps, replay = _race()
    replay.loc[replay.driver_code.eq("A") & replay.lap_number.ge(19), "gap_to_ahead_s"] = 1.0
    result = analyse_pit_timing_sensitivity(
        laps, replay, bootstrap_samples=100, max_new_extrapolation_laps=2
    )
    scenarios = result.scenarios.set_index("shift_laps")
    assert scenarios.loc[-3, "new_extrapolation_laps"] == 3
    assert not scenarios.loc[-3, "supported"]
    assert scenarios.loc[-2, "supported"]
    assert scenarios.loc[-2, "new_extrapolation_laps"] == 2
    assert result.summary.iloc[0]["best_supported_shift_laps"] == -2
    assert result.summary.iloc[0]["boundary_minimum"]


def test_actual_baseline_must_pass_extrapolation_gate() -> None:
    laps, replay = _race()
    result = analyse_pit_timing_sensitivity(laps, replay, max_old_extrapolation_laps=0)
    assert result.summary.iloc[0]["exclusion_reason"] == "unsupported_actual_baseline"
    assert result.summary.iloc[0]["actual_old_extrapolation_laps"] == 1
    assert not result.scenarios.supported.any()
    assert result.scenarios.delta_vs_actual_sec.isna().all()


def test_no_supported_alternative_does_not_publish_a_conclusion() -> None:
    laps, replay = _race()
    replay.loc[replay.driver_code.eq("A") & replay.lap_number.ge(19), "gap_to_ahead_s"] = 1.0
    result = analyse_pit_timing_sensitivity(
        laps, replay, max_old_extrapolation_laps=1, max_new_extrapolation_laps=0
    )
    assert result.summary.iloc[0]["exclusion_reason"] == "no_supported_alternative"
    assert not result.scenarios.supported.any()


@pytest.mark.parametrize(("valid", "requested"), [(0, 100), (80, 100), (100, 200)])
def test_empty_or_partial_bootstrap_is_explicitly_excluded(
    monkeypatch: pytest.MonkeyPatch, valid: int, requested: int
) -> None:
    laps, replay = _race()
    monkeypatch.setattr(
        pit_timing,
        "_bootstrap_deltas",
        lambda *args, **kwargs: pit_timing._BootstrapResult(
            {shift: np.zeros(valid) for shift in range(-3, 4)}, requested, requested * 10
        ),
    )
    result = analyse_pit_timing_sensitivity(laps, replay, bootstrap_samples=requested)
    summary = result.summary.iloc[0]
    assert summary["exclusion_reason"] == "insufficient_valid_bootstrap_samples"
    assert summary["bootstrap_valid_samples"] == valid
    assert summary["bootstrap_attempted_samples"] == requested * 10
    assert not result.scenarios.supported.any()
    assert result.scenarios.delta_p25_sec.isna().all()


def test_flat_model_splits_bootstrap_credit_instead_of_claiming_certain_actual_win() -> None:
    laps, replay = _race()
    laps.loc[laps.driver_code.eq("A") & laps.lap_number.ne(9), "lap_time_sec"] = 100.0
    summary, _ = _result(laps, replay)
    assert summary["best_supported_shift_laps"] == 0
    assert summary["best_shift_win_pct"] == pytest.approx(100 / 7)
    assert not summary["boundary_minimum"]
    assert summary["timing_signal"] == "No meaningful directional signal"
    assert pit_timing._best_shift({-1: -1.0, 1: -1.0, 0: 0.0}) == -1
    assert pit_timing._tied_minima({-1: -1.0, 1: -1.0, 0: 0.0}) == [-1, 1]


def test_bootstrap_rejects_nonfinite_fit_draws(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = pd.DataFrame(
        {"tyre_life": [1.0, 2.0], "post_stop_offset": [7, 8], "field_pace_residual_sec": [0.0, 1.0]}
    )
    monkeypatch.setattr(pit_timing, "_fit", lambda *args: (np.nan, 0.0, 0.0))
    result = pit_timing._bootstrap_deltas(
        frame, frame, frame, actual_in_age=3, actual_out_lap=4, samples=2, seed=1
    )
    assert result.valid == 0
    assert result.attempted == 20


@pytest.mark.parametrize(
    ("boundary", "valid", "expected"),
    [(True, 300, "medium"), (False, 299, "medium"), (False, 300, "high")],
)
def test_high_evidence_requires_interior_minimum_and_300_draws(
    boundary: bool, valid: int, expected: str
) -> None:
    assert (
        pit_timing._confidence(
            pd.Series({"new_tyre_fresh": True}), 6, 6, 100.0, 0.0, 0.0, 100.0, boundary, valid
        )
        == expected
    )


def test_exact_bootstrap_completion_threshold_is_publishable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    laps, replay = _race()
    monkeypatch.setattr(
        pit_timing,
        "_bootstrap_deltas",
        lambda *args, **kwargs: pit_timing._BootstrapResult(
            {shift: np.zeros(180) for shift in range(-3, 4)}, 200, 2000
        ),
    )
    result = analyse_pit_timing_sensitivity(laps, replay, bootstrap_samples=200)
    assert result.summary.iloc[0]["eligible"]
    assert result.summary.iloc[0]["bootstrap_valid_samples"] == 180


@pytest.mark.parametrize("limit", [-1.0, np.nan, np.inf])
def test_rejects_invalid_extrapolation_limits(limit: float) -> None:
    laps, replay = _race()
    with pytest.raises(ValueError, match="finite and non-negative"):
        analyse_pit_timing_sensitivity(laps, replay, max_old_extrapolation_laps=limit)


def test_bootstrap_seed_is_stable_when_another_race_is_added() -> None:
    laps, replay = _race()
    target = laps.driver_code.eq("A")
    laps.loc[target, "lap_time_sec"] += laps.loc[target, "lap_number"].mod(3) * 0.07
    baseline = analyse_pit_timing_sensitivity(laps, replay, bootstrap_samples=100)
    combined = analyse_pit_timing_sensitivity(
        pd.concat([laps.assign(round=0), laps]).sample(frac=1, random_state=3),
        pd.concat([replay.assign(round=0), replay]),
        bootstrap_samples=100,
    )
    pd.testing.assert_frame_equal(
        baseline.summary,
        combined.summary.loc[combined.summary["round"].eq(1)].reset_index(drop=True),
    )
    pd.testing.assert_frame_equal(
        baseline.scenarios,
        combined.scenarios.loc[combined.scenarios["round"].eq(1)].reset_index(drop=True),
    )


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("yellow", "non_green_evaluation_window"),
        ("unknown", "unsupported_compound"),
        ("short", "incomplete_evaluation_window"),
    ],
)
def test_keeps_excluded_stops_with_reason(mutation: str, reason: str) -> None:
    laps, replay = _race()
    if mutation == "yellow":
        laps.loc[laps["driver_code"].eq("A") & laps["lap_number"].eq(12), "track_status"] = "4"
    elif mutation == "unknown":
        laps.loc[laps["driver_code"].eq("A") & laps["lap_number"].ge(9), "compound"] = "UNKNOWN"
    else:
        laps = laps.loc[~(laps["driver_code"].eq("A") & laps["lap_number"].eq(18))]

    summary, scenarios = _result(laps, replay)

    assert not summary["eligible"]
    assert summary["exclusion_reason"] == reason
    assert not scenarios["supported"].any()
    assert set(scenarios["exclusion_reason"]) == {reason}


def test_missing_clean_air_evidence_excludes_model() -> None:
    laps, replay = _race()
    traffic = replay["driver_code"].eq("A") & replay["lap_number"].between(2, 7)
    replay.loc[traffic, "gap_to_ahead_s"] = 1.0

    summary, _ = _result(laps, replay)

    assert not summary["eligible"]
    assert summary["exclusion_reason"] == "insufficient_old_reference_laps"


def test_empty_input_has_typed_contract() -> None:
    laps, replay = _race()
    result = analyse_pit_timing_sensitivity(laps.iloc[0:0], replay.iloc[0:0])

    assert result.summary.empty
    assert result.scenarios.empty
    assert str(result.summary["eligible"].dtype) == "boolean"
    assert str(result.summary["season"].dtype) == "Int64"
    assert str(result.scenarios["delta_vs_actual_sec"].dtype) == "float64"


def test_rejects_duplicate_driver_lap_rows() -> None:
    laps, replay = _race()
    duplicated = pd.concat([laps, laps.iloc[[0]]], ignore_index=True)

    with pytest.raises(ValueError, match="duplicate driver-lap"):
        analyse_pit_timing_sensitivity(duplicated, replay)


def _seed_warehouse(path: Path) -> Settings:
    laps, replay = _race()
    laps["session"] = "R"
    races = pd.DataFrame([{"season": 2026, "round": 1, "race_name": "Test Grand Prix"}])
    codes = pd.DataFrame(
        [
            {"season": 2026, "driver_id": driver, "driver_code": driver, "driver_name": name}
            for driver, name in laps[["driver_code", "driver_name"]]
            .drop_duplicates()
            .itertuples(index=False)
        ]
    )
    stops = _stops().rename(columns={"driver_code": "driver_id"})
    connection = duckdb.connect(str(path))
    try:
        connection.execute("create schema staging")
        connection.execute("create schema marts")
        for name, frame in {
            "laps": laps,
            "replay": replay,
            "races": races,
            "codes": codes,
            "stops": stops,
        }.items():
            connection.register(name, frame)
        connection.execute("create table staging.stg_laps as select * from laps")
        connection.execute("create table marts.race_replay as select * from replay")
        connection.execute("create table staging.stg_races as select * from races")
        connection.execute("create table staging.stg_driver_codes as select * from codes")
        connection.execute("create table staging.stg_pitstops as select * from stops")
    finally:
        connection.close()
    return Settings(warehouse="duckdb", duckdb_path=path)


def test_builder_materialises_both_marts_and_incremental_preserves_races(tmp_path: Path) -> None:
    settings = _seed_warehouse(tmp_path / "pit-timing.duckdb")

    result = build_pit_timing_sensitivity(2026, 1, settings=settings)

    assert list(result.summary.columns) == PIT_TIMING_COLUMNS
    assert len(result.summary) == 1
    assert len(result.scenarios) == 7
    persisted = read_query("select * from marts.pit_timing_sensitivity", settings)
    assert bool(persisted.iloc[0]["eligible"])

    connection = duckdb.connect(str(settings.duckdb_path))
    try:
        connection.execute(
            "insert into marts.pit_timing_sensitivity "
            "select * replace (2 as round) from marts.pit_timing_sensitivity"
        )
        connection.execute(
            "insert into marts.pit_timing_scenarios "
            "select * replace (2 as round) from marts.pit_timing_scenarios"
        )
    finally:
        connection.close()

    build_pit_timing_sensitivity_incremental(2026, 1, settings=settings)

    summary_rounds = read_query(
        "select round, count(*) as rows from marts.pit_timing_sensitivity "
        "group by round order by round",
        settings,
    )
    scenario_rounds = read_query(
        "select round, count(*) as rows from marts.pit_timing_scenarios "
        "group by round order by round",
        settings,
    )
    assert summary_rounds.to_dict("records") == [
        {"round": 1, "rows": 1},
        {"round": 2, "rows": 1},
    ]
    assert scenario_rounds.to_dict("records") == [
        {"round": 1, "rows": 7},
        {"round": 2, "rows": 7},
    ]
