from __future__ import annotations

import copy
from typing import Any

import duckdb
import pytest
from scripts.racecraft_review import empty_review, make_packet, score


@pytest.fixture
def panel() -> Any:
    reference = {
        "windows": [
            {
                "id": "pair",
                "season": 2025,
                "round": 1,
                "pair": ["A", "B"],
                "anchor_driver": "A",
                "lap_min": 1,
                "lap_max": 1,
                "expected": ["must not leak"],
                "note": "detector hints must not leak",
            }
        ]
    }
    packet = make_packet(reference)
    reviews = [empty_review(packet), empty_review(packet)]
    for index, review in enumerate(reviews):
        review.update(reviewer_id=f"human-{index}", independent_of_detector=True)
        review["windows"][0].update(
            complete=True,
            uncertainties=[],
            footage_url="https://example.com/footage",
            footage_start_s=0,
            footage_end_s=50,
            reviewed_at="2026-09-14",
            events=[
                {
                    "passer_code": "B",
                    "passed_code": "A",
                    "lap_number": 1,
                    "footage_t_s": 10,
                    "held_until_s": 14,
                }
            ],
        )
    with duckdb.connect() as connection:
        connection.execute("create schema marts")
        connection.execute(
            "create table marts.race_replay as select 2025 season, 1 round, driver_code, t_s, 1 lap_number, case when driver_code='A' then 1 else 2 end running_order from (values ('A'),('B')) d(driver_code), range(51) t(t_s)"
        )
        connection.execute(
            "create table marts.race_overtakes as select 2025 season, 1 round, 10.0 t_s, 'B' passer_code, 'A' passed_code"
        )
        yield connection, packet, reviews


def test_blind_packet_excludes_previous_labels_and_hints(panel: Any) -> None:
    _, packet, _ = panel
    assert "expected" not in packet["protocol"]["windows"][0]
    assert "note" not in packet["protocol"]["windows"][0]


def test_pending_reviews_do_not_turn_detections_into_false_positives(panel: Any) -> None:
    connection, packet, _ = panel
    result = score(connection, packet, [empty_review(packet), empty_review(packet)])
    assert result["scored_windows"] == 0
    assert result["counts"] is None
    assert result["selected_window_precision"] is None


def test_agreed_exhaustive_window_counts_both_missed_and_extra_detections(panel: Any) -> None:
    connection, packet, reviews = panel
    connection.execute("update marts.race_overtakes set t_s=30")
    connection.execute("insert into marts.race_overtakes values (2025,1,20,'A','B')")
    for review in reviews:
        review["windows"][0]["events"].append(
            {
                "passer_code": "A",
                "passed_code": "B",
                "lap_number": 1,
                "footage_t_s": 30,
                "held_until_s": 34,
            }
        )
    result = score(connection, packet, reviews)
    assert result["counts"] == {"true_positive": 1, "false_positive": 1, "false_negative": 1}
    assert result["selected_window_precision"] == 0.5
    assert result["selected_window_recall"] == 0.5
    assert result["population_accuracy"] is None


def test_agreed_negative_window_with_no_events_has_no_precision_denominator(panel: Any) -> None:
    connection, packet, reviews = panel
    connection.execute("delete from marts.race_overtakes")
    for review in reviews:
        review["windows"][0]["events"] = []
    result = score(connection, packet, reviews)
    assert result["scored_windows"] == 1
    assert result["selected_window_precision"] is None
    assert result["selected_window_recall"] is None


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("independence", "two_independent_reviews_required"),
        ("disagreement", "reviewer_disagreement"),
        ("uncertainty", "incomplete_or_uncertain_review"),
        ("short_hold", "insufficient_hold_evidence"),
        ("missing_footage", "missing_footage"),
    ],
)
def test_unresolved_review_is_not_scored(panel: Any, mutation: str, reason: str) -> None:
    connection, packet, reviews = panel
    row = reviews[0]["windows"][0]
    if mutation == "independence":
        reviews[0]["independent_of_detector"] = False
    elif mutation == "disagreement":
        row["events"] = []
    elif mutation == "uncertainty":
        row["uncertainties"] = ["Occluded"]
    elif mutation == "short_hold":
        row["events"][0]["held_until_s"] = 12
    else:
        row["footage_url"] = None
    result = score(connection, packet, reviews)
    assert result["counts"] is None
    assert result["windows"][0]["reason"] == reason


def test_missing_partner_remains_unscored_despite_agreement(panel: Any) -> None:
    connection, packet, reviews = panel
    connection.execute("delete from marts.race_replay where driver_code='B'")
    assert score(connection, packet, reviews)["scored_windows"] == 0


def test_unknown_order_does_not_become_a_missed_pass(panel: Any) -> None:
    connection, packet, reviews = panel
    connection.execute(
        "update marts.race_replay set running_order=null where driver_code='B' and t_s=10"
    )
    result = score(connection, packet, reviews)
    assert result["counts"] is None
    assert result["windows"][0]["reason"] == "missing_order_evidence"


def test_nonfinite_footage_bounds_are_not_accepted(panel: Any) -> None:
    connection, packet, reviews = panel
    reviews[0]["windows"][0]["footage_end_s"] = float("inf")
    with pytest.raises(ValueError):
        score(connection, packet, reviews)


def test_same_reviewer_cannot_supply_both_votes(panel: Any) -> None:
    connection, packet, reviews = panel
    reviews[1]["reviewer_id"] = " HUMAN-0 "
    with pytest.raises(ValueError, match="distinct reviewers"):
        score(connection, packet, reviews)


def test_protocol_and_review_scope_cannot_silently_change(panel: Any) -> None:
    connection, packet, reviews = panel
    changed = copy.deepcopy(packet)
    changed["protocol"]["windows"][0]["lap_max"] = 2
    with pytest.raises(ValueError, match="frozen protocol"):
        score(connection, changed, reviews)
    reviews[0]["windows"] = []
    with pytest.raises(ValueError, match="coverage mismatch"):
        score(connection, packet, reviews)
