"""Tests for the traffic-adjusted race-pace analysis."""

from __future__ import annotations

from analytics.traffic import analyse_traffic_adjusted_pace
import numpy as np
import pandas as pd
import pytest


TRAFFIC_LAPS = {3, 5, 7, 9, 11}


def _laps() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for lap in range(1, 13):
        for driver in ("A", "B", "C"):
            traffic_offset = float((lap - 1) // 2) if driver == "A" and lap in TRAFFIC_LAPS else 0
            rows.append(
                {
                    "season": 2026,
                    "round": 1,
                    "race_name": "Test Grand Prix",
                    "driver_code": driver,
                    "team": f"Team {driver}",
                    "lap_number": lap,
                    "stint": 1,
                    "compound": "MEDIUM",
                    "tyre_life": lap,
                    "lap_time_sec": 100.0 + traffic_offset,
                }
            )
    return pd.DataFrame(rows)


def _replay(tick_s: float = 1.0) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for lap in range(1, 13):
        for offset in np.arange(0.0, 100.0, tick_s):
            for order, driver in enumerate(("B", "A", "C"), start=1):
                if driver == "A":
                    gap = 1.0 if lap in TRAFFIC_LAPS else 4.0
                elif order == 1:
                    gap = 0.0
                else:
                    gap = 4.0
                rows.append(
                    {
                        "season": 2026,
                        "round": 1,
                        "driver_code": driver,
                        "lap_number": lap,
                        "stint": 1,
                        "t_s": (lap - 1) * 100 + float(offset),
                        "running_order": order,
                        "gap_to_ahead_s": gap,
                    }
                )
    return pd.DataFrame(rows)


def test_publishes_clean_air_pace_and_paired_traffic_association() -> None:
    result = analyse_traffic_adjusted_pace(_laps(), _replay())

    driver = result.summary.loc[result.summary["driver_code"].eq("A")].iloc[0]
    assert driver["eligible_laps"] == 11
    assert driver["traffic_laps"] == 5
    assert driver["clean_air_laps"] == 6
    assert driver["mixed_laps"] == 0
    assert driver["matched_traffic_laps"] == 5
    assert driver["traffic_exposure_pct"] == pytest.approx(500 / 11)
    assert driver["traffic_adjusted_pace_delta_sec"] == pytest.approx(0.0)
    assert driver["traffic_associated_delta_sec_per_lap"] == pytest.approx(3.0)
    assert driver["traffic_associated_p25_sec"] == pytest.approx(2.0)
    assert driver["traffic_associated_p75_sec"] == pytest.approx(4.0)
    assert driver["confidence"] == "low"

    evidence = result.evidence.loc[result.evidence["driver_code"].eq("A")]
    assert 1 not in evidence["lap_number"].tolist()
    assert evidence.loc[evidence["lap_number"].eq(3), "matched_clean_laps"].iloc[0] == 2
    assert evidence.loc[evidence["lap_number"].eq(5), "paired_traffic_delta_sec"].iloc[0] == pytest.approx(2.0)


def test_leader_is_clean_but_zero_gap_follower_is_unknown() -> None:
    replay = _replay()
    zero_gap = (replay["driver_code"] == "A") & (replay["lap_number"] == 2)
    replay.loc[zero_gap, "gap_to_ahead_s"] = 0.0

    result = analyse_traffic_adjusted_pace(_laps(), replay)

    states = result.evidence.set_index(["driver_code", "lap_number"])["air_state"]
    assert set(result.evidence.loc[result.evidence["driver_code"].eq("B"), "air_state"]) == {
        "clean_air"
    }
    assert states.loc[("A", 2)] == "mixed"


def test_dead_band_and_under_covered_laps_are_mixed() -> None:
    replay = _replay()
    dead_band = (replay["driver_code"] == "A") & (replay["lap_number"] == 3)
    replay.loc[dead_band, "gap_to_ahead_s"] = 2.0
    sparse = (replay["driver_code"] == "A") & (replay["lap_number"] == 5)
    replay = replay.drop(replay.loc[sparse].index[70:])

    result = analyse_traffic_adjusted_pace(_laps(), replay)

    states = result.evidence.set_index(["driver_code", "lap_number"])["air_state"]
    assert states.loc[("A", 3)] == "mixed"
    assert states.loc[("A", 5)] == "mixed"
    driver = result.summary.loc[result.summary["driver_code"].eq("A")].iloc[0]
    assert driver["clean_air_laps"] + driver["traffic_laps"] + driver["mixed_laps"] == driver[
        "eligible_laps"
    ]
    assert driver["confidence"] == "insufficient"
    assert pd.isna(driver["traffic_associated_delta_sec_per_lap"])


@pytest.mark.parametrize("tick_s", [0.5, 1.0, 2.0])
def test_classification_is_invariant_to_replay_tick_size(tick_s: float) -> None:
    result = analyse_traffic_adjusted_pace(_laps(), _replay(tick_s))
    driver = result.summary.loc[result.summary["driver_code"].eq("A")].iloc[0]

    assert driver["traffic_laps"] == 5
    assert driver["clean_air_laps"] == 6
    assert 95.0 <= driver["replay_coverage_pct"] <= 100.0


def test_excludes_pit_transition_laps_using_all_replay_laps() -> None:
    laps = _laps()
    laps.loc[(laps["driver_code"] == "A") & laps["lap_number"].ge(7), "stint"] = 2
    replay = _replay()
    replay.loc[(replay["driver_code"] == "A") & replay["lap_number"].ge(7), "stint"] = 2

    result = analyse_traffic_adjusted_pace(laps, replay)

    driver_laps = result.evidence.loc[result.evidence["driver_code"].eq("A"), "lap_number"]
    assert 6 not in driver_laps.tolist()
    assert 7 not in driver_laps.tolist()
    assert 12 in driver_laps.tolist()


def test_matching_crosses_stints_but_not_compound_or_tyre_window() -> None:
    laps = _laps()
    replay = _replay()
    second_stint = (laps["driver_code"] == "A") & laps["lap_number"].ge(7)
    laps.loc[second_stint, "stint"] = 2
    laps.loc[second_stint, "tyre_life"] -= 6
    replay.loc[(replay["driver_code"] == "A") & replay["lap_number"].ge(7), "stint"] = 2
    laps.loc[(laps["driver_code"] == "A") & (laps["lap_number"] == 8), "compound"] = "HARD"

    result = analyse_traffic_adjusted_pace(laps, replay)
    a = result.evidence.loc[result.evidence["driver_code"].eq("A")].set_index("lap_number")

    assert a.loc[9, "matched_clean_laps"] >= 1
    assert a.loc[9, "matched_clean_delta_sec"] == pytest.approx(0.0)


def test_negative_association_is_not_clipped() -> None:
    laps = _laps()
    traffic = (laps["driver_code"] == "A") & laps["lap_number"].isin(TRAFFIC_LAPS)
    laps.loc[traffic, "lap_time_sec"] = 99.0

    result = analyse_traffic_adjusted_pace(laps, _replay())
    driver = result.summary.loc[result.summary["driver_code"].eq("A")].iloc[0]

    assert driver["traffic_associated_delta_sec_per_lap"] == pytest.approx(-1.0)


def test_final_lap_linger_does_not_change_classification() -> None:
    replay = _replay()
    linger_rows = replay.loc[
        (replay["driver_code"] == "A") & (replay["lap_number"] == 12)
    ].iloc[:50].copy()
    linger_rows["t_s"] += 1000
    linger_rows["gap_to_ahead_s"] = 1.0
    replay = pd.concat([replay, linger_rows], ignore_index=True)

    result = analyse_traffic_adjusted_pace(_laps(), replay)
    state = result.evidence.set_index(["driver_code", "lap_number"]).loc[("A", 12), "air_state"]
    assert state == "clean_air"


def test_validates_inputs_thresholds_and_empty_frames() -> None:
    laps = _laps()
    replay = _replay()
    with pytest.raises(ValueError, match="laps is missing"):
        analyse_traffic_adjusted_pace(laps.drop(columns="team"), replay)
    with pytest.raises(ValueError, match="replay is missing"):
        analyse_traffic_adjusted_pace(laps, replay.drop(columns="running_order"))
    with pytest.raises(ValueError, match="clean_air_gap_s"):
        analyse_traffic_adjusted_pace(laps, replay, traffic_gap_s=2, clean_air_gap_s=1)

    result = analyse_traffic_adjusted_pace(laps.iloc[0:0], replay)
    assert result.evidence.empty
    assert result.summary.empty
    assert "traffic_associated_delta_sec_per_lap" in result.summary.columns
