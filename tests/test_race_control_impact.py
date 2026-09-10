"""Tests for observed race-control impact analysis."""

from __future__ import annotations

import pandas as pd
import pytest
from analytics.race_control_impact import (
    RACE_CONTROL_IMPACT_COLUMNS,
    analyse_race_control_impact,
)


def _replay() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    states = {
        99.0: [("AAA", 1, 0.0, 5, 1, "MEDIUM", 12), ("BBB", 2, 8.0, 5, 1, "MEDIUM", 12)],
        100.0: [("AAA", 1, 0.0, 5, 1, "MEDIUM", 12), ("BBB", 2, 8.0, 5, 1, "MEDIUM", 12)],
        160.0: [("BBB", 1, 0.0, 6, 2, "HARD", 1), ("AAA", 2, 1.5, 6, 1, "MEDIUM", 13)],
        161.0: [("BBB", 1, 0.0, 6, 2, "HARD", 1), ("AAA", 2, 1.5, 6, 1, "MEDIUM", 13)],
        200.0: [("BBB", 1, 0.0, 7, 2, "HARD", 2), ("AAA", 2, 2.0, 7, 1, "MEDIUM", 14)],
        220.0: [("BBB", 1, 0.0, 7, 2, "HARD", 2), ("AAA", 2, 2.0, 7, 1, "MEDIUM", 14)],
    }
    for t_s, drivers in states.items():
        for code, position, gap, lap, stint, compound, tyre_life in drivers:
            rows.append(
                {
                    "season": 2026,
                    "round": 1,
                    "race_name": "Test GP",
                    "driver_code": code,
                    "driver_name": f"Driver {code}",
                    "team": f"Team {code}",
                    "t_s": t_s,
                    "lap_number": lap,
                    "stint": stint,
                    "compound": compound,
                    "tyre_life": tyre_life,
                    "running_order": position,
                    "gap_to_leader_s": gap,
                }
            )
    return pd.DataFrame(rows)


def _control(messages: list[tuple[float, int, str, str | None]]) -> pd.DataFrame:
    columns = ["season", "round", "t_s", "category", "flag", "message", "lap"]
    return pd.DataFrame(
        [
            {
                "season": 2026,
                "round": 1,
                "t_s": t_s,
                "category": "SafetyCar" if flag is None else "Flag",
                "flag": flag,
                "message": message,
                "lap": lap,
            }
            for t_s, lap, message, flag in messages
        ],
        columns=columns,
    )


def test_measures_safety_car_position_gap_and_stop_impact() -> None:
    control = _control(
        [(100.0, 5, "SAFETY CAR DEPLOYED", None), (150.0, 5, "SAFETY CAR IN THIS LAP", None)]
    )
    result = analyse_race_control_impact(_replay(), control)

    bbb = result.loc[result["driver_code"].eq("BBB")].iloc[0]
    assert len(result) == 2
    assert bbb["event_type"] == "Safety Car"
    assert bbb["position_before"] == 2
    assert bbb["position_after"] == 1
    assert bbb["positions_gained"] == 1
    assert bbb["gap_compression_s"] == pytest.approx(8.0)
    assert bool(bbb["stopped_during_event"])
    assert bbb["compound_after"] == "HARD"
    assert bbb["outcome_label"] == "Gained positions"
    assert bbb["confidence"] == "High"


@pytest.mark.parametrize(
    ("start_message", "end_message"),
    [
        ("VSC DEPLOYED", "VSC ENDING"),
        ("VIRTUAL SAFETY CAR DEPLOYED", "VIRTUAL SAFETY CAR ENDING"),
    ],
)
def test_parses_both_virtual_safety_car_message_variants(
    start_message: str, end_message: str
) -> None:
    result = analyse_race_control_impact(
        _replay(), _control([(100.0, 5, start_message, None), (160.0, 6, end_message, None)])
    )

    assert result["event_type"].unique().tolist() == ["VSC"]
    assert result["event_complete"].all()


def test_red_flag_uses_the_actual_restart_marker() -> None:
    control = _control(
        [
            (100.0, 5, "RED FLAG - RACE SUSPENDED", None),
            (140.0, 5, "RACE WILL RESUME AT 15:30", None),
            (160.0, 6, "STANDING START", None),
        ]
    )
    result = analyse_race_control_impact(_replay(), control)

    assert result["event_type"].unique().tolist() == ["Red Flag"]
    assert result["end_t_s"].unique().tolist() == [160.0]
    assert result["confidence"].unique().tolist() == ["Medium"]


def test_red_flag_interrupts_open_safety_car_and_keeps_both_as_evidence() -> None:
    control = _control(
        [
            (100.0, 5, "SAFETY CAR DEPLOYED", None),
            (160.0, 6, "RED FLAG", "RED"),
            (200.0, 7, "ROLLING START", None),
        ]
    )
    result = analyse_race_control_impact(_replay(), control)

    sc = result.loc[result["event_type"].eq("Safety Car")]
    red = result.loc[result["event_type"].eq("Red Flag")]
    assert not sc["eligible"].any()
    assert sc["exclusion_reason"].unique().tolist() == ["Interrupted by red flag"]
    assert red["eligible"].all()


def test_unclosed_event_is_retained_but_excluded() -> None:
    result = analyse_race_control_impact(_replay(), _control([(100.0, 5, "VSC DEPLOYED", None)]))

    assert len(result) == 2
    assert not result["event_complete"].any()
    assert not result["eligible"].any()
    assert result["exclusion_reason"].unique().tolist() == ["No matching end message"]


def test_missing_post_event_driver_is_not_silently_dropped() -> None:
    replay = _replay().loc[lambda frame: ~(frame["driver_code"].eq("AAA") & frame["t_s"].gt(100))]
    control = _control([(100.0, 5, "VSC DEPLOYED", None), (160.0, 6, "VSC ENDING", None)])
    result = analyse_race_control_impact(replay, control)

    aaa = result.loc[result["driver_code"].eq("AAA")].iloc[0]
    assert not bool(aaa["active_after"])
    assert not bool(aaa["eligible"])
    assert aaa["outcome_label"] == "No post-event timing"


def test_ignores_unrelated_safety_car_mentions() -> None:
    control = _control([(100.0, 5, "CAR 4 INVESTIGATED - SAFETY CAR INFRINGEMENT", None)])
    result = analyse_race_control_impact(_replay(), control)

    assert result.empty
    assert result.columns.tolist() == RACE_CONTROL_IMPACT_COLUMNS


def test_empty_inputs_keep_a_typed_schema() -> None:
    result = analyse_race_control_impact(_replay().iloc[0:0], _control([]))

    assert result.empty
    assert result.columns.tolist() == RACE_CONTROL_IMPACT_COLUMNS
    assert str(result["season"].dtype) == "Int64"
    assert str(result["eligible"].dtype) == "boolean"
    assert str(result["gap_compression_s"].dtype) == "float64"


def test_validates_input_contracts() -> None:
    with pytest.raises(ValueError, match="replay is missing columns"):
        analyse_race_control_impact(_replay().drop(columns="team"), _control([]))
    with pytest.raises(ValueError, match="race_control is missing columns"):
        analyse_race_control_impact(_replay(), _control([]).drop(columns="lap"))
