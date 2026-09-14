"""Tests for the traffic-adjusted race-pace analysis."""

from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest
from analytics.pipeline import (
    build_traffic_adjusted_pace,
    build_traffic_adjusted_pace_incremental,
)
from analytics.traffic import (
    _add_controlled_delta,
    _summarise,
    analyse_traffic_adjusted_pace,
    classify_representative_lap_air,
)
from ingestion.config import Settings
from ingestion.loaders.warehouse import read_query

TRAFFIC_LAPS = {3, 5, 7, 9, 11}


def test_peer_median_excludes_self_and_resists_one_outlier() -> None:
    laps = _laps().query("lap_number == 2").copy()
    laps["lap_time_sec"] = [90.0, 100.0, 102.0, 1000.0]
    evidence = _add_controlled_delta(laps).set_index("driver_code")
    assert evidence.loc["A", "peer_count"] == 3
    assert evidence.loc["A", "peer_lap_median_sec"] == 102.0
    assert evidence.loc["A", "peer_lap_avg_sec"] == pytest.approx(1202 / 3)
    assert evidence.loc["A", "controlled_pace_delta_sec"] == -12.0
    assert evidence.loc["D", "peer_lap_median_sec"] == 100.0
    shuffled = _add_controlled_delta(laps.sample(frac=1, random_state=42))
    pd.testing.assert_frame_equal(
        evidence.sort_index(), shuffled.set_index("driver_code").sort_index()
    )


def test_peer_minimum_three_default_and_two_explicit() -> None:
    laps = _laps().query("driver_code != 'D'")
    replay = _replay().query("driver_code != 'D'")
    assert analyse_traffic_adjusted_pace(laps, replay).evidence.empty
    evidence = analyse_traffic_adjusted_pace(laps, replay, min_peer_drivers=2).evidence
    assert len(evidence) == 33
    assert evidence["peer_count"].eq(2).all()
    assert evidence["peer_lap_avg_sec"].equals(evidence["peer_lap_median_sec"])


@pytest.mark.parametrize("minimum", [0, 1, 2.5, True])
def test_invalid_peer_minimum_is_rejected_even_for_empty_input(minimum: int) -> None:
    with pytest.raises(ValueError, match="min_peer_drivers"):
        analyse_traffic_adjusted_pace(_laps().iloc[:0], _replay(), min_peer_drivers=minimum)


@pytest.mark.parametrize("conflicting", [False, True])
def test_duplicate_driver_laps_cannot_inflate_peer_count(conflicting: bool) -> None:
    laps = _laps()
    extra = laps.iloc[[4]].copy()
    if conflicting:
        extra["lap_time_sec"] += 20
    duplicated = pd.concat([laps, extra], ignore_index=True)
    with pytest.raises(ValueError, match="one observation per driver and lap"):
        analyse_traffic_adjusted_pace(duplicated, _replay())


def test_duplicate_replay_ticks_and_input_permutation_do_not_change_estimates() -> None:
    replay = _replay()
    duplicated = pd.concat([replay, replay.iloc[::20]], ignore_index=True)
    expected = analyse_traffic_adjusted_pace(_laps(), replay)
    actual = analyse_traffic_adjusted_pace(
        _laps().sample(frac=1, random_state=8), duplicated.sample(frac=1, random_state=9)
    )
    pd.testing.assert_frame_equal(expected.evidence, actual.evidence)
    pd.testing.assert_frame_equal(expected.summary, actual.summary)


def test_explicit_pit_boundary_excludes_visit_without_stint_change() -> None:
    laps = _laps()
    laps["is_pit_boundary"] = laps["driver_code"].eq("A") & laps["lap_number"].isin([6, 7])
    result = classify_representative_lap_air(laps, _replay())
    assert result.loc[result["driver_code"].eq("A"), "lap_number"].isin([6, 7]).sum() == 0
    assert result.loc[result["driver_code"].eq("B"), "lap_number"].isin([6, 7]).sum() == 2


def _laps() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for lap in range(1, 13):
        for driver in ("A", "B", "C", "D"):
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
            for order, driver in enumerate(("B", "A", "C", "D"), start=1):
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
    assert evidence.loc[evidence["lap_number"].eq(5), "paired_traffic_delta_sec"].iloc[
        0
    ] == pytest.approx(2.0)


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


@pytest.mark.parametrize(
    "column,value",
    [("gap_to_ahead_s", np.inf), ("running_order", np.inf), ("running_order", 1.5)],
)
def test_invalid_gap_or_rank_cannot_establish_clean_air(column: str, value: float) -> None:
    replay = _replay()
    replay[column] = replay[column].astype(float)
    selected = replay.driver_code.eq("A") & replay.lap_number.eq(2)
    replay.loc[selected, column] = value
    result = classify_representative_lap_air(_laps(), replay)
    row = result.loc[result.driver_code.eq("A") & result.lap_number.eq(2)].iloc[0]
    assert row.air_state == "mixed"
    assert row.valid_context_samples == 0
    assert pd.isna(row.median_gap_to_ahead_s)


@pytest.mark.parametrize("column", ["running_order", "gap_to_ahead_s"])
def test_sparse_usable_context_cannot_classify_an_entire_lap(column: str) -> None:
    laps = _laps().query("lap_number == 2")
    replay = _replay().query("lap_number == 2").copy()
    missing = replay.driver_code.eq("A") & replay.t_s.mod(10).ne(0)
    replay.loc[missing, column] = np.nan
    result = classify_representative_lap_air(laps, replay)
    row = result.loc[result.driver_code.eq("A")].iloc[0]
    assert row.context_samples == 100
    assert row.valid_context_samples == 10
    assert row.replay_coverage_pct == 100
    assert row.air_state == "mixed"


def test_conflicting_replay_context_is_not_resolved_by_row_order() -> None:
    replay = _replay()
    conflict = replay.iloc[[400]].copy()
    conflict["gap_to_ahead_s"] = 0.2
    with pytest.raises(ValueError, match="Conflicting replay context"):
        classify_representative_lap_air(_laps(), pd.concat([replay, conflict], ignore_index=True))


@pytest.mark.parametrize("compound", ["none", " NaN ", "<NA>", "NaT", "UNKNOWN", ""])
def test_textual_missing_compounds_are_not_representative(compound: str) -> None:
    laps = _laps()
    laps.loc[laps.driver_code.eq("A"), "compound"] = compound
    result = classify_representative_lap_air(laps, _replay())
    assert not result.driver_code.eq("A").any()


@pytest.mark.parametrize(
    "parameter,value",
    [
        ("traffic_gap_s", np.nan),
        ("clean_air_gap_s", np.inf),
        ("clean_air_lap_share", np.nan),
        ("min_replay_coverage", np.nan),
    ],
)
def test_nonfinite_context_thresholds_are_rejected(parameter: str, value: float) -> None:
    with pytest.raises(ValueError):
        classify_representative_lap_air(_laps(), _replay(), **{parameter: value})


@pytest.mark.parametrize("column", ["lap_number", "stint", "tyre_life"])
@pytest.mark.parametrize("value", [np.inf, 2.5])
def test_invalid_lap_counters_are_not_used_as_observations(column: str, value: float) -> None:
    laps = _laps()
    laps[column] = laps[column].astype(float)
    laps.loc[laps.driver_code.eq("A"), column] = value
    # Avoid deliberately introducing duplicate keys while checking field validity.
    if column == "lap_number":
        laps = laps.drop_duplicates(["season", "round", "driver_code", "lap_number"])
    result = classify_representative_lap_air(laps, _replay())
    assert not result.driver_code.eq("A").any()


@pytest.mark.parametrize("value", [np.nan, np.inf])
def test_nonfinite_matching_window_is_rejected(value: float) -> None:
    with pytest.raises(ValueError):
        analyse_traffic_adjusted_pace(_laps(), _replay(), tyre_age_window=value)


def test_clean_only_driver_has_publishable_clean_pace_without_association() -> None:
    result = analyse_traffic_adjusted_pace(_laps(), _replay())
    leader = result.summary.loc[result.summary["driver_code"].eq("B")].iloc[0]
    assert leader["clean_air_laps"] == 11
    assert leader["clean_air_eligible"]
    assert leader["clean_air_confidence"] == "medium"
    assert pd.notna(leader["traffic_adjusted_pace_delta_sec"])
    assert not leader["traffic_association_eligible"]
    assert leader["traffic_association_confidence"] == leader["confidence"] == "insufficient"
    assert pd.isna(leader["traffic_associated_delta_sec_per_lap"])


def test_configured_publication_minimum_precedes_sample_strength_labels() -> None:
    result = analyse_traffic_adjusted_pace(_laps(), _replay(), min_publish_laps=12)
    leader = result.summary.loc[result.summary["driver_code"].eq("B")].iloc[0]
    assert leader["clean_air_laps"] == 11
    assert not leader["clean_air_eligible"]
    assert leader["clean_air_confidence"] == "insufficient"
    assert pd.isna(leader["traffic_adjusted_pace_delta_sec"])


@pytest.mark.parametrize(
    ("clean_count", "matched_count", "clean_strength", "association_strength"),
    [
        (4, 12, "insufficient", "insufficient"),
        (5, 5, "low", "low"),
        (7, 7, "low", "low"),
        (8, 8, "medium", "medium"),
        (11, 11, "medium", "medium"),
        (12, 12, "high", "high"),
        (12, 4, "high", "insufficient"),
        (12, 8, "high", "medium"),
    ],
)
def test_metric_specific_sample_strength_boundaries(
    clean_count: int, matched_count: int, clean_strength: str, association_strength: str
) -> None:
    evidence = analyse_traffic_adjusted_pace(_laps(), _replay()).evidence
    driver = evidence.loc[evidence["driver_code"].eq("A")]
    clean = driver.loc[driver["air_state"].eq("clean_air")].iloc[[0]]
    traffic = driver.loc[driver["air_state"].eq("traffic")].iloc[[0]]
    samples = pd.concat([clean] * clean_count + [traffic] * matched_count, ignore_index=True)
    summary = _summarise(samples, min_publish_laps=5, traffic_gap_s=1.5, clean_air_gap_s=3.0).iloc[
        0
    ]
    assert summary["clean_air_confidence"] == clean_strength
    assert summary["traffic_association_confidence"] == association_strength
    assert summary["confidence"] == association_strength
    assert bool(summary["clean_air_eligible"]) == (clean_count >= 5)
    assert bool(summary["traffic_association_eligible"]) == (min(clean_count, matched_count) >= 5)
    assert pd.notna(summary["traffic_adjusted_pace_delta_sec"]) == (clean_count >= 5)
    assert pd.notna(summary["traffic_associated_delta_sec_per_lap"]) == (
        min(clean_count, matched_count) >= 5
    )


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
    assert (
        driver["clean_air_laps"] + driver["traffic_laps"] + driver["mixed_laps"]
        == driver["eligible_laps"]
    )
    assert driver["confidence"] == "insufficient"
    assert pd.isna(driver["traffic_associated_delta_sec_per_lap"])


def test_public_air_context_precedes_same_compound_peer_filter() -> None:
    laps = _laps()
    laps.loc[laps["driver_code"].eq("A"), "compound"] = "HARD"

    context = classify_representative_lap_air(laps, _replay())
    result = analyse_traffic_adjusted_pace(laps, _replay())

    assert set(context["driver_code"]) == {"A", "B", "C", "D"}
    assert "air_state" in context
    assert "A" not in set(result.evidence["driver_code"])


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
    linger_rows = (
        replay.loc[(replay["driver_code"] == "A") & (replay["lap_number"] == 12)].iloc[:50].copy()
    )
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


def _seed_warehouse(path: Path) -> Settings:
    connection = duckdb.connect(str(path))
    try:
        connection.execute("create schema marts")
        connection.execute("create schema staging")
        connection.register("laps", _laps())
        connection.register("replay", _replay())
        connection.execute("create table marts.mart_lap_times as select * from laps")
        connection.execute("create table staging.stg_laps as select *, 'R' as session from laps")
        connection.execute("create table marts.race_replay as select * from replay")
    finally:
        connection.close()
    return Settings(warehouse="duckdb", duckdb_path=path)


def test_builder_materialises_both_traffic_marts(tmp_path: Path) -> None:
    settings = _seed_warehouse(tmp_path / "traffic.duckdb")

    result = build_traffic_adjusted_pace(2026, 1, settings=settings)

    summary = read_query("select * from marts.traffic_adjusted_pace", settings)
    evidence = read_query("select * from marts.traffic_adjusted_laps", settings)
    assert len(summary) == len(result.summary) == 4
    assert len(evidence) == len(result.evidence) == 44
    assert not summary["traffic_adjusted_pace_delta_sec"].isna().all()


def test_builder_excludes_recorded_stop_without_stint_change(tmp_path: Path) -> None:
    settings = _seed_warehouse(tmp_path / "actual-stop.duckdb")
    with duckdb.connect(str(settings.duckdb_path)) as connection:
        connection.execute(
            "create table staging.stg_driver_codes as "
            "select 2026 season, 'driver_a' driver_id, 'A' driver_code"
        )
        connection.execute(
            "create table staging.stg_pitstops as "
            "select 2026 season, 1 round, 'driver_a' driver_id, 6 pit_lap, 25.0 duration_sec"
        )
    result = build_traffic_adjusted_pace(2026, 1, settings=settings)
    assert not (
        result.evidence["driver_code"].eq("A") & result.evidence["lap_number"].isin([6, 7])
    ).any()


def test_incremental_builder_preserves_other_races(tmp_path: Path) -> None:
    settings = _seed_warehouse(tmp_path / "traffic-incremental.duckdb")
    result = build_traffic_adjusted_pace(2026, 1, settings=settings)
    summary_copy = result.summary.copy().assign(round=2)
    evidence_copy = result.evidence.copy().assign(round=2)
    connection = duckdb.connect(str(settings.duckdb_path))
    try:
        connection.register("summary_copy", summary_copy)
        connection.register("evidence_copy", evidence_copy)
        connection.execute(
            "insert into marts.traffic_adjusted_pace by name select * from summary_copy"
        )
        connection.execute(
            "insert into marts.traffic_adjusted_laps by name select * from evidence_copy"
        )
    finally:
        connection.close()

    build_traffic_adjusted_pace_incremental(2026, 1, settings=settings)

    rounds = read_query(
        "select round, count(*) as rows from marts.traffic_adjusted_pace "
        "group by round order by round",
        settings,
    )
    assert rounds["round"].tolist() == [1, 2]
    assert rounds["rows"].tolist() == [4, 4]
