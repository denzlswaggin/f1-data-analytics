"""Tests for observed race-control impact analysis."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import duckdb
import pandas as pd
import pytest
from analytics.pipeline import (
    build_race_control_impact,
    build_race_control_impact_incremental,
)
from analytics.race_control_impact import (
    RACE_CONTROL_EVENT_COLUMNS,
    RACE_CONTROL_IMPACT_COLUMNS,
    RaceControlImpactResult,
    _estimated_lap_deficits,
    analyse_race_control_impact,
)
from ingestion.config import Settings
from ingestion.loaders.warehouse import read_query


def _replay() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    states = {
        99.0: [("AAA", 1, 0.0, 5, 1, "MEDIUM", 12), ("BBB", 2, 8.0, 5, 1, "MEDIUM", 12)],
        100.0: [("AAA", 1, 0.0, 5, 1, "MEDIUM", 12), ("BBB", 2, 8.0, 5, 1, "MEDIUM", 12)],
        140.0: [("AAA", 1, 0.0, 5, 1, "MEDIUM", 12), ("BBB", 2, 5.0, 5, 2, "HARD", 1)],
        150.0: [("AAA", 1, 0.0, 5, 1, "MEDIUM", 12), ("BBB", 2, 4.0, 5, 2, "HARD", 1)],
        200.0: [("BBB", 1, 0.0, 6, 2, "HARD", 2), ("AAA", 2, 1.5, 6, 1, "MEDIUM", 13)],
        230.0: [("BBB", 1, 0.0, 7, 2, "HARD", 3), ("AAA", 2, 1.5, 7, 1, "MEDIUM", 14)],
        260.0: [("BBB", 1, 0.0, 8, 2, "HARD", 4), ("AAA", 2, 1.5, 8, 1, "MEDIUM", 15)],
        300.0: [("BBB", 1, 0.0, 9, 2, "HARD", 5), ("AAA", 2, 2.0, 9, 1, "MEDIUM", 16)],
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
                    "lap_progress": 0.1 if position == 1 else 0.05,
                    "stint": stint,
                    "compound": compound,
                    "tyre_life": tyre_life,
                    "running_order": position,
                    "gap_to_leader_s": gap,
                }
            )
    return pd.DataFrame(rows)


def _control(messages: Sequence[tuple[float, int, str, str | None]]) -> pd.DataFrame:
    columns = [
        "season",
        "round",
        "race_name",
        "t_s",
        "category",
        "flag",
        "message",
        "lap",
    ]
    return pd.DataFrame(
        [
            {
                "season": 2026,
                "round": 1,
                "race_name": "Test GP",
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


def _laps(*, clean: bool = True) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "season": 2026,
                "round": 1,
                "driver_code": driver,
                "lap_number": lap,
                "track_status": status,
                "lap_start_t_s": start,
                "lap_end_t_s": end,
            }
            for driver in ("AAA", "BBB")
            for lap, status, start, end in (
                (5, "4", 0, 200),
                (6, "1", 200, 230),
                (7, "1" if clean else "12", 230, 260),
                (8, "1", 260, 300),
            )
        ]
    )


def _analyse(
    messages: Sequence[tuple[float, int, str, str | None]],
    *,
    replay: pd.DataFrame | None = None,
    laps: pd.DataFrame | None = None,
) -> RaceControlImpactResult:
    return analyse_race_control_impact(
        _replay() if replay is None else replay,
        _control(messages),
        _laps() if laps is None else laps,
        min_event_drivers=2,
    )


def test_measures_two_lap_safety_car_position_gap_and_stop_impact() -> None:
    result = _analyse(
        [(100.0, 5, "SAFETY CAR DEPLOYED", None), (150.0, 5, "SAFETY CAR IN THIS LAP", None)]
    )

    event = result.events.iloc[0]
    bbb = result.evidence.loc[result.evidence["driver_code"].eq("BBB")].iloc[0]
    assert event["post_checkpoint_lap"] == 8
    assert event["post_checkpoint_t_s"] == 260.0
    assert bool(event["eligible"])
    assert bbb["positions_gained"] == 1
    assert bbb["raw_gap_gain_s"] == pytest.approx(8.0)
    assert pd.isna(bbb["field_adjusted_gap_gain_s"])
    assert event["time_comparable_driver_count"] == 2
    assert not event["time_eligible"]
    assert bool(bbb["pitted_during_intervention"])
    assert bbb["outcome_label"] == "Observed position gain"


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
    result = _analyse([(100.0, 5, start_message, None), (150.0, 5, end_message, None)])

    assert result.events["event_type"].tolist() == ["VSC"]
    assert result.events["event_status"].tolist() == ["complete"]


def test_red_flag_uses_restart_marker_and_suppresses_time_gain() -> None:
    result = _analyse(
        [
            (100.0, 5, "RED FLAG - RACE SUSPENDED", None),
            (130.0, 5, "RACE WILL RESUME AT 15:30", None),
            (150.0, 5, "STANDING START", None),
        ]
    )

    assert result.events["end_t_s"].tolist() == [150.0]
    assert result.events["confidence"].tolist() == ["Medium"]
    assert result.evidence["raw_gap_gain_s"].isna().all()
    assert result.evidence["field_adjusted_gap_gain_s"].isna().all()


def test_red_flag_interrupts_open_safety_car() -> None:
    result = _analyse(
        [
            (100.0, 5, "SAFETY CAR DEPLOYED", None),
            (150.0, 5, "RED FLAG", "RED"),
            (200.0, 6, "ROLLING START", None),
        ]
    )

    safety_car = result.events.loc[result.events["event_type"].eq("Safety Car")].iloc[0]
    assert safety_car["event_status"] == "interrupted"
    assert not bool(safety_car["eligible"])
    assert safety_car["exclusion_reason"] == "Interrupted by red flag"


def test_recovery_interrupted_by_next_event_is_excluded() -> None:
    result = _analyse(
        [
            (100.0, 5, "VSC DEPLOYED", None),
            (150.0, 5, "VSC ENDING", None),
            (200.0, 6, "VSC DEPLOYED", None),
            (230.0, 7, "VSC ENDING", None),
        ]
    )

    first = result.events.iloc[0]
    assert not bool(first["eligible"])
    assert first["exclusion_reason"] == "Recovery interrupted by another neutralisation"


def test_unclosed_event_is_retained_without_driver_headline() -> None:
    result = _analyse([(100.0, 5, "VSC DEPLOYED", None)])

    assert result.events["event_status"].tolist() == ["unclosed"]
    assert not result.events["eligible"].any()
    assert not result.evidence["eligible"].any()


def test_missing_post_event_driver_is_retained() -> None:
    replay = _replay().loc[lambda frame: ~(frame["driver_code"].eq("AAA") & frame["t_s"].gt(100))]
    result = _analyse(
        [(100.0, 5, "VSC DEPLOYED", None), (150.0, 5, "VSC ENDING", None)],
        replay=replay,
    )

    aaa = result.evidence.loc[result.evidence["driver_code"].eq("AAA")].iloc[0]
    assert not bool(aaa["active_after"])
    assert aaa["exclusion_reason"] == "No post-event timing"


def test_lap_deficit_change_suppresses_time_but_keeps_position() -> None:
    replay = _replay()
    replay.loc[replay["driver_code"].eq("AAA") & replay["t_s"].eq(260.0), "lap_number"] = 7
    result = _analyse(
        [(100.0, 5, "VSC DEPLOYED", None), (150.0, 5, "VSC ENDING", None)],
        replay=replay,
    )

    aaa = result.evidence.loc[result.evidence["driver_code"].eq("AAA")].iloc[0]
    assert bool(aaa["eligible"])
    assert bool(aaa["lap_deficit_changed"])
    assert pd.isna(aaa["raw_gap_gain_s"])


def test_unclean_recovery_excludes_event_but_retains_evidence() -> None:
    result = _analyse(
        [(100.0, 5, "VSC DEPLOYED", None), (150.0, 5, "VSC ENDING", None)],
        laps=_laps(clean=False),
    )

    assert not bool(result.events["recovery_clean"].iloc[0])
    assert result.events["confidence"].tolist() == ["Low"]
    assert not result.events["eligible"].any()
    assert not result.evidence["time_eligible"].any()
    assert len(result.evidence) == 2


@pytest.mark.parametrize(
    ("leader_lap", "leader_progress", "driver_lap", "driver_progress", "expected"),
    [
        (32, 0.7002, 32, 0.6209, 0),  # Bahrain/Russell before deployment.
        (38, 0.0002, 37, 0.9860, 0),  # Same racing lap despite finish-line seam.
        (38, 0.2, 37, 0.0, 1),
        (38, 0.2, 36, 0.0, 2),
        (38, 0.0, 37, 0.0, None),  # Positive whole-lap boundary is uncertain.
        (38, 0.0, 37, 0.02, None),
        (38, 0.02, 37, 0.0, None),
        (38, 0.0, 38, 0.1, None),  # Invalid ordering.
        (38, 0.0, 37, 1.1, None),
        (38, 0.0, 37, None, None),
        (38, None, 37, 0.9, None),
    ],
)
def test_estimated_deficit_uses_continuous_distance_and_guards_boundaries(
    leader_lap: int,
    leader_progress: float | None,
    driver_lap: int,
    driver_progress: float | None,
    expected: int | None,
) -> None:
    frame = pd.DataFrame(
        [
            {
                "driver_code": "A",
                "running_order": 1,
                "t_s": 100.0,
                "lap_number": leader_lap,
                "lap_progress": leader_progress,
            },
            {
                "driver_code": "B",
                "running_order": 2,
                "t_s": 100.0,
                "lap_number": driver_lap,
                "lap_progress": driver_progress,
            },
        ]
    )
    assert _estimated_lap_deficits(frame).get("B") == expected


def test_misaligned_and_nullable_progress_is_not_treated_as_known_deficit() -> None:
    frame = _replay().loc[lambda f: f.t_s.eq(100)].copy()
    frame.loc[frame.driver_code.eq("BBB"), "t_s"] = 99.0
    assert _estimated_lap_deficits(frame)["BBB"] is None
    frame["lap_progress"] = pd.Series(pd.NA, index=frame.index, dtype="Float64")
    assert not _estimated_lap_deficits(frame)


def _five_driver_replay() -> pd.DataFrame:
    replay = _replay()
    extra = []
    for position, code in enumerate(("CCC", "DDD", "EEE"), start=3):
        extra.append(
            replay.loc[replay.driver_code.eq("AAA")].assign(
                driver_code=code,
                running_order=position,
                lap_progress=0.03,
                gap_to_leader_s=lambda f: f.t_s.map(lambda t: 14.0 if t <= 150 else 3.0),
            )
        )
    return pd.concat([replay, *extra], ignore_index=True)


def test_time_median_needs_five_comparable_drivers_not_just_positions() -> None:
    messages = [(100.0, 5, "VSC DEPLOYED", None), (150.0, 5, "VSC ENDING", None)]
    replay = _five_driver_replay()
    good = _analyse(messages, replay=replay)
    assert good.events.iloc[0]["time_comparable_driver_count"] == 5
    assert good.events.iloc[0]["time_eligible"]
    assert good.evidence["time_eligible"].all()
    assert good.evidence["field_adjusted_gap_gain_s"].tolist() == pytest.approx(
        (good.evidence.raw_gap_gain_s - good.evidence.raw_gap_gain_s.median()).tolist()
    )

    replay.loc[replay.driver_code.eq("EEE") & replay.t_s.eq(260), "lap_progress"] = float("nan")
    limited = _analyse(messages, replay=replay)
    assert limited.evidence["eligible"].all()
    assert limited.events.iloc[0]["time_comparable_driver_count"] == 4
    assert limited.evidence["field_adjusted_gap_gain_s"].isna().all()
    assert not limited.evidence["time_eligible"].any()
    missing = limited.evidence.loc[limited.evidence.driver_code.eq("EEE")].iloc[0]
    assert pd.isna(missing["lap_deficit_changed"])
    assert "unavailable" in missing["time_exclusion_reason"]


def test_single_comparable_driver_does_not_publish_zero_adjusted_gain() -> None:
    replay = _five_driver_replay()
    replay.loc[replay.driver_code.ne("AAA") & replay.t_s.eq(100), "lap_progress"] = float("nan")
    result = _analyse(
        [(100.0, 5, "VSC DEPLOYED", None), (150.0, 5, "VSC ENDING", None)], replay=replay
    )
    assert result.events.iloc[0]["time_comparable_driver_count"] == 1
    assert result.evidence["field_adjusted_gap_gain_s"].isna().all()


@pytest.mark.parametrize(
    "mutation", ["null_status", "missing_lap", "missing_end", "broken_continuity"]
)
def test_incomplete_leader_recovery_is_excluded(mutation: str) -> None:
    laps = _laps()
    target = laps.driver_code.eq("BBB") & laps.lap_number.eq(7)
    if mutation == "missing_lap":
        laps = laps.loc[~target]
    else:
        column, value = {
            "null_status": ("track_status", None),
            "missing_end": ("lap_end_t_s", None),
            "broken_continuity": ("lap_start_t_s", 232),
        }[mutation]
        laps.loc[target, column] = value
    result = _analyse([(100.0, 5, "VSC DEPLOYED", None), (150.0, 5, "VSC ENDING", None)], laps=laps)
    assert not result.events.iloc[0]["eligible"]
    assert not result.events.iloc[0]["recovery_clean"]


def test_recovery_uses_actual_time_not_other_drivers_lap_numbers() -> None:
    laps = _laps()
    laps.loc[laps.driver_code.eq("AAA") & laps.lap_number.eq(7), ["lap_number", "track_status"]] = [
        2,
        "12",
    ]
    messages = [(100.0, 5, "VSC DEPLOYED", None), (150.0, 5, "VSC ENDING", None)]
    assert not _analyse(messages, laps=laps).events.iloc[0]["recovery_clean"]
    late = (
        _laps()
        .iloc[[0]]
        .assign(
            driver_code="LATE",
            lap_number=7,
            lap_start_t_s=1000,
            lap_end_t_s=float("nan"),
            track_status=None,
        )
    )
    assert _analyse(messages, laps=pd.concat([_laps(), late])).events.iloc[0]["recovery_clean"]


def test_end_message_lap_is_not_used_as_recovery_clock() -> None:
    result = _analyse([(100.0, 5, "VSC DEPLOYED", None), (150.0, 1, "VSC ENDING", None)])
    assert result.events.iloc[0]["recovery_clean"]


def test_stale_leader_at_end_signal_does_not_define_recovery() -> None:
    replay = _replay().loc[lambda frame: ~frame.t_s.eq(150)]
    result = _analyse(
        [(100.0, 5, "VSC DEPLOYED", None), (150.0, 5, "VSC ENDING", None)], replay=replay
    )
    assert result.events.iloc[0]["exclusion_reason"] == "Two-lap recovery unavailable"


def test_sampled_crossing_cannot_hide_reference_lap_starting_before_end_signal() -> None:
    replay = _replay()
    replay.loc[replay.t_s.eq(200), "t_s"] = 151.0
    laps = _laps().astype({"lap_start_t_s": "float64"})
    laps.loc[laps.driver_code.eq("BBB") & laps.lap_number.eq(6), "lap_start_t_s"] = 149.5
    result = _analyse(
        [(100.0, 5, "VSC DEPLOYED", None), (150.0, 5, "VSC ENDING", None)], replay=replay, laps=laps
    )
    assert not result.events.iloc[0]["recovery_clean"]


def test_straddling_previous_sc_lap_does_not_poison_green_leader_laps() -> None:
    # BBB leads two fully green laps [200, 260]. AAA's SC lap ends at 205;
    # its aggregate flag does not establish any yellow within [200, 205].
    laps = _laps()
    laps.loc[laps.driver_code.eq("AAA"), ["lap_start_t_s", "lap_end_t_s"]] += 5.0
    laps.loc[laps.driver_code.eq("AAA") & laps.lap_number.eq(5), "lap_end_t_s"] = float("nan")
    result = _analyse([(100.0, 5, "VSC DEPLOYED", None), (150.0, 5, "VSC ENDING", None)], laps=laps)
    assert result.events.iloc[0]["recovery_clean"]


def test_untimed_lap_starting_inside_recovery_remains_unknown() -> None:
    extra = (
        _laps()
        .iloc[[0]]
        .assign(
            driver_code="UNKNOWN", lap_start_t_s=210.0, lap_end_t_s=float("nan"), track_status="1"
        )
    )
    result = _analyse(
        [(100.0, 5, "VSC DEPLOYED", None), (150.0, 5, "VSC ENDING", None)],
        laps=pd.concat([_laps(), extra], ignore_index=True),
    )
    assert not result.events.iloc[0]["recovery_clean"]


def test_ignores_unrelated_safety_car_mentions() -> None:
    result = _analyse([(100.0, 5, "CAR 4 - SAFETY CAR INFRINGEMENT", None)])

    assert result.events.empty
    assert result.evidence.empty


def test_empty_inputs_keep_typed_schemas() -> None:
    result = analyse_race_control_impact(_replay().iloc[0:0], _control([]), _laps().iloc[0:0])

    assert result.events.columns.tolist() == RACE_CONTROL_EVENT_COLUMNS
    assert result.evidence.columns.tolist() == RACE_CONTROL_IMPACT_COLUMNS
    assert str(result.events["eligible"].dtype) == "boolean"
    assert str(result.evidence["field_adjusted_gap_gain_s"].dtype) == "float64"


def test_validates_contracts_and_minimum_sample() -> None:
    with pytest.raises(ValueError, match="replay is missing columns"):
        analyse_race_control_impact(_replay().drop(columns="team"), _control([]), _laps())
    with pytest.raises(ValueError, match="race_control is missing columns"):
        analyse_race_control_impact(_replay(), _control([]).drop(columns="lap"), _laps())
    with pytest.raises(ValueError, match="laps is missing columns"):
        analyse_race_control_impact(_replay(), _control([]), _laps().drop(columns="track_status"))
    with pytest.raises(ValueError, match="min_event_drivers"):
        analyse_race_control_impact(_replay(), _control([]), _laps(), min_event_drivers=0)


def _seed_warehouse(path: Path) -> Settings:
    settings = Settings(warehouse="duckdb", duckdb_path=path)
    replay = _replay()
    laps = _laps().assign(
        session="R",
        team=lambda frame: "Team " + frame["driver_code"],
        lap_start_sec=lambda frame: 1000.0 + frame["lap_start_t_s"],
        lap_time_sec=lambda frame: frame["lap_end_t_s"] - frame["lap_start_t_s"],
    )
    races = pd.DataFrame([{"season": 2026, "round": 1, "race_name": "Test GP"}])
    codes = pd.DataFrame(
        [
            {
                "season": 2026,
                "driver_code": code,
                "driver_name": f"Driver {code}",
            }
            for code in ("AAA", "BBB")
        ]
    )
    messages = _control([(100.0, 5, "VSC DEPLOYED", None), (150.0, 5, "VSC ENDING", None)]).assign(
        session="R", session_time_sec=lambda frame: frame["t_s"] + 1000.0
    )

    connection = duckdb.connect(str(path))
    try:
        connection.execute("create schema staging")
        connection.execute("create schema marts")
        for schema, name, frame in (
            ("marts", "race_replay", replay),
            ("staging", "stg_laps", laps),
            ("staging", "stg_races", races),
            ("staging", "stg_driver_codes", codes),
            ("staging", "stg_race_control", messages),
        ):
            connection.register("incoming", frame)
            connection.execute(f"create table {schema}.{name} as select * from incoming")
            connection.unregister("incoming")
    finally:
        connection.close()
    return settings


def test_builder_materialises_both_race_control_marts(tmp_path: Path) -> None:
    settings = _seed_warehouse(tmp_path / "race-control.duckdb")

    result = build_race_control_impact(2026, 1, settings=settings)
    events = read_query("select * from marts.race_control_events", settings)
    evidence = read_query("select * from marts.race_control_impact", settings)

    assert len(events) == len(result.events) == 1
    assert len(evidence) == len(result.evidence) == 2
    assert events["event_type"].tolist() == ["VSC"]


def test_incremental_builder_preserves_other_races(tmp_path: Path) -> None:
    settings = _seed_warehouse(tmp_path / "race-control-incremental.duckdb")
    result = build_race_control_impact(2026, 1, settings=settings)
    connection = duckdb.connect(str(settings.duckdb_path))
    try:
        for table, frame in (
            ("race_control_events", result.events.assign(round=2)),
            ("race_control_impact", result.evidence.assign(round=2)),
        ):
            connection.register("copy", frame)
            connection.execute(f"insert into marts.{table} by name select * from copy")
            connection.unregister("copy")
    finally:
        connection.close()

    build_race_control_impact_incremental(2026, 1, settings=settings)

    events = read_query(
        "select round, count(*) as rows from marts.race_control_events "
        "group by round order by round",
        settings,
    )
    evidence = read_query(
        "select round, count(*) as rows from marts.race_control_impact "
        "group by round order by round",
        settings,
    )
    assert events[["round", "rows"]].values.tolist() == [[1, 1], [2, 1]]
    assert evidence[["round", "rows"]].values.tolist() == [[1, 2], [2, 2]]
