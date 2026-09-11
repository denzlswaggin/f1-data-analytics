from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import duckdb
import pytest
from scripts.report_event_windows import evaluate, main


@pytest.fixture
def context() -> Any:
    connection = duckdb.connect()
    connection.execute("create schema marts")
    connection.execute("""create table marts.pit_lap_context
        (season integer, round integer, driver_code varchar,
         lap_number integer, is_pit_in_lap boolean)""")
    connection.execute("""insert into marts.pit_lap_context
        select 2025, 1, 'PIA', i, i in (2,4) from range(1,6) t(i)""")
    reference = {
        "schema_version": 1,
        "windows": [
            {
                "id": "one",
                "season": 2025,
                "round": 1,
                "driver": "PIA",
                "kind": "pit_entry",
                "lap_min": 1,
                "lap_max": 5,
                "expected_laps": [2, 3],
                "source_url": "https://example.org/pits",
                "complete": True,
            }
        ],
    }
    yield connection, reference
    connection.close()


def test_exact_one_to_one_errors(context: Any) -> None:
    connection, reference = context
    result = evaluate(connection, reference)
    assert result["counts"] == {"true_positive": 1, "false_negative": 1, "false_positive": 1}
    assert result["precision"] == result["recall"] == 0.5
    assert result["windows"][0]["missed_expected_laps"] == [3]


def test_duplicate_detections_are_extra_false_positives(context: Any) -> None:
    connection, reference = context
    connection.execute("insert into marts.pit_lap_context values (2025,1,'PIA',2,true)")
    result = evaluate(connection, reference)
    assert result["counts"]["false_positive"] == 2
    assert result["counts"]["true_positive"] == 1
    assert result["windows"][0]["duplicate_candidate_laps"] == [2]


@pytest.mark.parametrize("deleted_laps", ["lap_number=1", "lap_number=3", "true"])
def test_missing_even_negative_context_unscored(context: Any, deleted_laps: str) -> None:
    connection, reference = context
    connection.execute(f"delete from marts.pit_lap_context where {deleted_laps}")
    result = evaluate(connection, reference)
    assert result["scored_windows"] == 0
    assert result["unscored_windows"] == ["one"]
    assert result["precision"] is result["recall"] is None
    assert all(value == 0 for value in result["counts"].values())
    assert result["windows"][0]["true_positive"] is None
    assert result["windows"][0]["missing_laps"]


def test_complete_empty_window_has_no_invented_true_negatives(context: Any) -> None:
    connection, reference = context
    reference["windows"][0]["expected_laps"] = []
    connection.execute("update marts.pit_lap_context set is_pit_in_lap=false")
    result = evaluate(connection, reference)
    assert result["scored_windows"] == 1
    assert result["precision"] is result["recall"] is None
    assert "true_negative" not in result["counts"]


def test_unknown_flag_does_not_become_negative_evidence(context: Any) -> None:
    connection, reference = context
    connection.execute("update marts.pit_lap_context set is_pit_in_lap=null where lap_number=1")
    result = evaluate(connection, reference)
    assert result["scored_windows"] == 0
    assert result["windows"][0]["unknown_flag_laps"] == [1]
    assert result["windows"][0]["unscored_reason"] == "unknown_pit_flags"
    assert result["precision"] is result["recall"] is None


def test_no_expected_events_with_detections(context: Any) -> None:
    connection, reference = context
    reference["windows"][0]["expected_laps"] = []
    result = evaluate(connection, reference)
    assert result["precision"] == 0
    assert result["recall"] is None
    assert result["counts"]["false_positive"] == 2


def test_no_detections_with_expected_events(context: Any) -> None:
    connection, reference = context
    connection.execute("update marts.pit_lap_context set is_pit_in_lap=false")
    result = evaluate(connection, reference)
    assert result["precision"] is None
    assert result["recall"] == 0
    assert result["counts"]["false_negative"] == 2


def test_outside_window_and_other_driver_ignored(context: Any) -> None:
    connection, reference = context
    connection.execute("""insert into marts.pit_lap_context values
        (2025,1,'PIA',6,true),(2025,1,'NOR',1,true),(2025,2,'PIA',1,true)""")
    assert evaluate(connection, reference)["scored_candidate_events"] == 2


@pytest.mark.parametrize(
    "key,value",
    [
        ("id", True),
        ("id", ""),
        ("season", True),
        ("round", 0),
        ("lap_min", 1.0),
        ("lap_max", False),
        ("lap_max", 0),
        ("expected_laps", [2, 2]),
        ("expected_laps", [True]),
        ("expected_laps", [6]),
        ("expected_laps", None),
        ("complete", False),
        ("complete", 1),
        ("kind", "overtake"),
        ("driver", ""),
        ("source_url", "not-a-url"),
    ],
)
def test_malformed_annotations_rejected(context: Any, key: str, value: Any) -> None:
    connection, reference = context
    reference["windows"][0][key] = value
    with pytest.raises(ValueError):
        evaluate(connection, reference)


@pytest.mark.parametrize("duplicate_id", [True, False])
def test_duplicate_ids_or_overlapping_windows_rejected(context: Any, duplicate_id: bool) -> None:
    connection, reference = context
    extra = copy.deepcopy(reference["windows"][0])
    if not duplicate_id:
        extra["id"] = "two"
    reference["windows"].append(extra)
    with pytest.raises(ValueError):
        evaluate(connection, reference)


def test_only_scored_windows_contribute_to_denominators(context: Any) -> None:
    connection, reference = context
    extra = copy.deepcopy(reference["windows"][0])
    extra.update(id="absent", driver="NOR", expected_laps=[1, 2, 3, 4])
    reference["windows"].append(extra)
    result = evaluate(connection, reference)
    assert result["scored_expected_events"] == result["scored_candidate_events"] == 2
    assert result["unscored_windows"] == ["absent"]


@pytest.mark.parametrize("version", [True, 1.0, 2, None])
def test_invalid_schema(context: Any, version: Any) -> None:
    connection, reference = context
    reference["schema_version"] = version
    with pytest.raises(ValueError):
        evaluate(connection, reference)


def test_cli_hash_normalizes_crlf_and_leaves_snapshot_unchanged(
    context: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    _, reference = context
    snapshot = tmp_path / "snapshot.duckdb"
    with duckdb.connect(str(snapshot)) as connection:
        connection.execute("create schema marts")
        connection.execute("""create table marts.pit_lap_context as
            select 2025 as season, 1 as round, 'PIA' as driver_code,
            i as lap_number, i in (2,4) as is_pit_in_lap from range(1,6) t(i)""")
        connection.execute("create schema dashboard")
        connection.execute("""create table dashboard.snapshot_metadata as
            select 'test-version' as version, '2026-01-01' as generated_at""")
    before = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    reference_path = tmp_path / "reference.json"
    text = json.dumps(reference, indent=2) + "\n"
    reference_path.write_bytes(text.replace("\n", "\r\n").encode())
    monkeypatch.setattr(
        "sys.argv", ["report", "--snapshot", str(snapshot), "--reference", str(reference_path)]
    )
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["reference_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert result["snapshot_metadata"][0][0] == "test-version"
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == before
