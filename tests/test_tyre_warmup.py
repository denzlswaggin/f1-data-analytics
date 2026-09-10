"""Tests for traffic-controlled tyre warm-up analysis."""

from __future__ import annotations

import pandas as pd
import pytest
from analytics.tyre_warmup import (
    TYRE_WARMUP_COLUMNS,
    TYRE_WARMUP_LAP_COLUMNS,
    analyse_tyre_warmup,
)


def _laps(
    *,
    compound: str = "HARD",
    fresh: bool = True,
    stint_end: int = 17,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "season": 2026,
                "round": 1,
                "race_name": "Test GP",
                "driver_code": "AAA",
                "driver_name": "Driver AAA",
                "team": "Test Team",
                "lap_number": lap,
                "stint": 2,
                "compound": compound,
                "tyre_life": lap - 9,
                "is_fresh_tyre": fresh,
                "lap_time_sec": 90.0,
                "track_status": "1",
            }
            for lap in range(10, stint_end + 1)
        ]
    )


def _traffic(
    deltas: dict[int, float] | None = None,
    states: dict[int, str] | None = None,
) -> pd.DataFrame:
    deltas = deltas or {11: 1.2, 12: 0.4, 13: 0.1, 14: 0.0, 15: -0.1}
    states = states or {}
    return pd.DataFrame(
        [
            {
                "season": 2026,
                "round": 1,
                "driver_code": "AAA",
                "stint": 2,
                "lap_number": lap,
                "air_state": states.get(lap, "clean_air"),
                "controlled_pace_delta_sec": delta,
                "replay_coverage_pct": 100.0,
            }
            for lap, delta in deltas.items()
        ]
    )


def test_measures_first_flying_loss_cost_and_time_to_stable() -> None:
    result = analyse_tyre_warmup(_laps(), _traffic())

    stint = result.summary.iloc[0]
    assert bool(stint["eligible"])
    assert stint["first_flying_lap"] == 11
    assert stint["stable_baseline_controlled_delta_sec"] == pytest.approx(0.0)
    assert stint["first_flying_loss_sec"] == pytest.approx(1.2)
    assert stint["second_flying_loss_sec"] == pytest.approx(0.4)
    assert stint["first_two_lap_warmup_cost_sec"] == pytest.approx(1.6)
    assert stint["time_to_stable_laps"] == 3
    assert stint["confidence"] == "High"


def test_out_lap_is_never_in_warmup_evidence() -> None:
    result = analyse_tyre_warmup(_laps(), _traffic())

    assert result.laps["lap_number"].min() == 11
    assert result.laps["stint_lap_offset"].tolist() == [1, 2, 3, 4, 5]


def test_requires_clean_air_on_first_flying_lap() -> None:
    result = analyse_tyre_warmup(_laps(), _traffic(states={11: "traffic"}))

    assert not bool(result.summary["eligible"].iloc[0])
    assert result.summary["exclusion_reason"].iloc[0] == "First flying lap was not in clean air"


def test_requires_two_clean_baseline_laps() -> None:
    result = analyse_tyre_warmup(_laps(), _traffic(states={13: "traffic", 14: "mixed"}))

    assert not bool(result.summary["eligible"].iloc[0])
    assert result.summary["exclusion_reason"].iloc[0] == "Fewer than two clean baseline laps"


@pytest.mark.parametrize(
    ("laps", "reason"),
    [
        (_laps(fresh=False), "Stint did not start on fresh tyres"),
        (_laps(compound="INTERMEDIATE"), "Unsupported or wet-weather compound"),
        (_laps(stint_end=15), "Stint shorter than 7 laps"),
    ],
)
def test_retains_ineligible_stints(laps: pd.DataFrame, reason: str) -> None:
    result = analyse_tyre_warmup(laps, _traffic())

    assert len(result.summary) == 1
    assert not bool(result.summary["eligible"].iloc[0])
    assert result.summary["exclusion_reason"].iloc[0] == reason


def test_non_green_lap_is_not_used_for_baseline() -> None:
    laps = _laps()
    laps.loc[laps["lap_number"].eq(13), "track_status"] = "12"
    result = analyse_tyre_warmup(laps, _traffic())

    lap = result.laps.loc[result.laps["lap_number"].eq(13)].iloc[0]
    assert not bool(lap["eligible"])
    assert lap["exclusion_reason"] == "Lap was not green"
    assert result.summary["baseline_laps"].iloc[0] == 2


def test_stable_crossover_requires_two_consecutive_laps() -> None:
    traffic = _traffic({11: 0.1, 12: 0.8, 13: 0.0, 14: 0.1, 15: -0.1})
    result = analyse_tyre_warmup(_laps(), traffic)

    assert result.summary["time_to_stable_laps"].iloc[0] == 3


def test_empty_result_has_stable_typed_schemas() -> None:
    result = analyse_tyre_warmup(_laps().iloc[0:0], _traffic().iloc[0:0])

    assert result.summary.columns.tolist() == TYRE_WARMUP_COLUMNS
    assert result.laps.columns.tolist() == TYRE_WARMUP_LAP_COLUMNS
    assert str(result.summary["eligible"].dtype) == "boolean"
    assert str(result.laps["warmup_delta_sec"].dtype) == "float64"


def test_validates_contracts_and_threshold() -> None:
    with pytest.raises(ValueError, match="laps is missing columns"):
        analyse_tyre_warmup(_laps().drop(columns="team"), _traffic())
    with pytest.raises(ValueError, match="traffic_laps is missing columns"):
        analyse_tyre_warmup(_laps(), _traffic().drop(columns="air_state"))
    with pytest.raises(ValueError, match="stable_band_sec"):
        analyse_tyre_warmup(_laps(), _traffic(), stable_band_sec=0)
