from __future__ import annotations

import copy
import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pytest
from scripts.compare_openf1_orders import compare, load_capture, position_timeline, utc_seconds

CAPTURE = Path("validation/openf1-austria-2025")


def observation(driver: int, seconds: float, rank: int | None) -> dict[str, Any]:
    return {
        "driver_number": driver,
        "position": rank,
        "date": datetime.fromtimestamp(seconds, UTC).isoformat(),
    }


def test_simultaneous_swaps_are_atomic_and_last_hold_is_censored() -> None:
    rows = {
        4: [observation(4, 0, 1), observation(4, 5, 2), observation(4, 17.625, 1)],
        81: [observation(81, 0, 2), observation(81, 5, 1), observation(81, 17.625, 2)],
    }
    result = position_timeline(rows, 1, 20)
    transitions = result["transitions"]
    assert [row["overtaking_driver_number"] for row in transitions] == [81, 4]
    assert transitions[0]["inferred_state_duration_s"] == 12.625
    assert not transitions[0]["right_censored"]
    assert transitions[1]["right_censored"]
    assert result["complete_source_coverage"] is None


def test_asynchronous_tied_ranks_do_not_invent_a_pass() -> None:
    result = position_timeline(
        {
            4: [observation(4, 0, 1), observation(4, 6, 2)],
            81: [observation(81, 0, 2), observation(81, 5, 1)],
        },
        1,
        10,
    )
    assert result["transitions"] == []
    assert result["ambiguous_or_missing_intervals"] == [{"start_utc_s": 5, "end_utc_s": 6}]


def test_missing_baseline_is_not_evidence_of_no_events() -> None:
    result = position_timeline({4: [], 81: []}, 1, 10)
    assert not result["baseline_available"]
    assert result["complete_source_coverage"] is None
    assert result["ambiguous_or_missing_intervals"]


def test_conflicting_updates_and_naive_dates_are_rejected() -> None:
    with pytest.raises(ValueError, match="Conflicting"):
        position_timeline({4: [observation(4, 0, 1), observation(4, 0, 2)], 81: []}, 1, 10)
    with pytest.raises(ValueError, match="timezone"):
        utc_seconds("2025-06-29T13:00:00")


def test_captured_sources_reject_modified_bytes(tmp_path: Path) -> None:
    shutil.copytree(CAPTURE, tmp_path / "capture")
    (tmp_path / "capture" / "position-4.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="integrity"):
        load_capture(tmp_path / "capture")


@pytest.fixture
def austria() -> Any:
    manifest, data = load_capture(CAPTURE)
    reference = json.loads(Path("validation/pass-windows-v1.json").read_text())
    window = reference["windows"][0]
    diagnostic = json.loads(
        Path("validation/racecraft-review-v1/austria-order-diagnostic.json").read_text()
    )
    with duckdb.connect() as connection:
        connection.execute("create schema staging")
        connection.execute("create schema marts")
        connection.execute(
            "create table staging.stg_races as select 2025 season,11 round,date '2025-06-29' race_date"
        )
        connection.execute(
            "create table staging.stg_laps(season int,round int,session varchar,driver_code varchar,driver_number int,lap_number int,lap_start_sec double)"
        )
        for code, number in [("NOR", 4), ("PIA", 81)]:
            connection.execute(
                "insert into staging.stg_laps values (2025,11,'R',?,?,1,?)",
                [code, number, diagnostic["race_origin_session_s"]],
            )
            for row in diagnostic["lap_inputs"]:
                if row["driver_code"] == code:
                    connection.execute(
                        "insert into staging.stg_laps values (2025,11,'R',?,?,?,?)",
                        [code, number, row["lap_number"], row["lap_start_sec"]],
                    )
        connection.execute(
            "create table marts.race_replay as select 2025 season,11 round,driver_code,t_s,running_order from (values ('NOR',1),('PIA',2)) d(driver_code,running_order),range(805,876) t(t_s)"
        )
        connection.execute(
            "create table marts.race_overtakes(season int,round int,t_s double,passer_code varchar,passed_code varchar)"
        )
        yield connection, manifest, data, window


def test_austria_source_reversal_is_present_but_not_video_truth(austria: Any) -> None:
    result = compare(*austria)
    assert len(result["source_position_timeline"]["transitions"]) == 2
    assert len(result["source_overtake_endpoint_rows"]) == 2
    assert result["snapshot_detected_pair_events"] == []
    assert result["clock_alignment"]["spread_s"] == pytest.approx(0.159, abs=0.00001)
    assert result["accuracy"] is None
    assert result["independent_video_validation"] is False


@pytest.mark.parametrize("failure", ["clock_drift", "missing_anchor", "wrong_race"])
def test_unsafe_alignment_does_not_produce_a_comparison(austria: Any, failure: str) -> None:
    connection, manifest, original, window = austria
    data = copy.deepcopy(original)
    if failure == "clock_drift":
        row = next(row for row in data["laps-81.json"] if row["lap_number"] == 12)
        row["date_start"] = (
            datetime.fromisoformat(row["date_start"]) + timedelta(seconds=2)
        ).isoformat()
    elif failure == "missing_anchor":
        data["laps-81.json"] = [row for row in data["laps-81.json"] if row["lap_number"] != 12]
    else:
        data["sessions.json"][0]["date_start"] = "2025-07-01T13:00:00+00:00"
    with pytest.raises(ValueError):
        compare(connection, manifest, data, window)
