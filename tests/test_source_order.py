import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from analytics.source_order import field_samples, pair_samples
from scripts.compare_openf1_orders import load_capture


def row(driver: int, second: float, **values: Any) -> dict[str, Any]:
    return {
        "driver_number": driver,
        "date": datetime.fromtimestamp(second, UTC).isoformat(),
        **values,
    }


def test_swap_invalidates_gap_even_when_pair_returns_to_original_order() -> None:
    positions = {
        4: [row(4, 0, position=1), row(4, 2, position=2), row(4, 3, position=1)],
        81: [row(81, 0, position=2), row(81, 2, position=1), row(81, 3, position=2)],
    }
    intervals = {4: [], 81: [row(81, 1, interval=0.5), row(81, 4, interval=0.7)]}
    samples = pair_samples(positions, intervals, [1, 3, 4, 8, 9])
    trailing = [s for s in samples if s["driver_number"] == 81]
    assert [s["gap_to_ahead_s"] for s in trailing] == [0.5, None, 0.7, 0.7, None]
    assert trailing[1]["gap_status"] == "interval_predates_order_change"
    assert trailing[-1]["gap_status"] == "stale_interval"
    assert not any(s["pressure_eligible"] for s in samples)


@pytest.mark.parametrize("value", [None, "+1 LAP", -1, float("inf"), True])
def test_invalid_interval_is_never_converted_to_seconds(value: Any) -> None:
    samples = pair_samples(
        {4: [row(4, 0, position=1)], 81: [row(81, 0, position=2)]},
        {4: [], 81: [row(81, 1, interval=value)]},
        [1],
    )
    assert samples[-1]["gap_to_ahead_s"] is None


@pytest.mark.parametrize("rank", [1, 3, None])
def test_ties_missing_and_nonadjacent_order_cannot_assign_gap(rank: int | None) -> None:
    samples = pair_samples(
        {4: [row(4, 0, position=1)], 81: [row(81, 0, position=rank)]},
        {4: [], 81: [row(81, 1, interval=0.5)]},
        [1],
    )
    assert samples[-1]["gap_to_ahead_s"] is None
    assert samples[-1]["ahead_driver_number"] is None


def test_future_and_conflicting_observations() -> None:
    positions = {4: [row(4, 0, position=1)], 81: [row(81, 0, position=2)]}
    intervals = {4: [], 81: [row(81, 2, interval=0.5)]}
    assert pair_samples(positions, intervals, [1])[-1]["gap_to_ahead_s"] is None
    positions[4].append(row(4, 0, position=2))
    with pytest.raises(ValueError, match="Conflicting"):
        pair_samples(positions, intervals, [1])


def test_frozen_austria_exchange_uses_new_opponent_interval() -> None:
    directory = Path("validation/openf1-austria-2025-intervals")
    manifest, data = load_capture(directory)
    report = json.loads((directory / "evaluation.json").read_text(encoding="utf-8"))
    offset = report["clock_alignment"]["utc_minus_replay_s"]
    samples = pair_samples(
        {d: data[f"position-{d}.json"] for d in manifest["drivers"]},
        {d: data[f"intervals-{d}.json"] for d in manifest["drivers"]},
        [offset + t for t in (821, 822, 834, 835)],
    )
    norris = [s for s in samples if s["driver_number"] == 4]
    assert [s["running_order"] for s in norris] == [1, 2, 2, 1]
    assert norris[1]["ahead_driver_number"] == 81
    assert norris[1]["gap_to_ahead_s"] == pytest.approx(0.037)
    assert (
        norris[1]["interval_observed_utc_s"]
        > report["transition_contexts"][0]["source_event"]["utc_s"]
    )
    assert norris[-1]["gap_to_ahead_s"] is None


def test_full_field_swap_assigns_new_opponent_and_invalidates_old_gaps() -> None:
    positions = {
        1: [row(1, 0, position=1)],
        4: [row(4, 0, position=2), row(4, 2, position=3)],
        81: [row(81, 0, position=3), row(81, 2, position=2)],
    }
    intervals = {
        1: [],
        4: [row(4, 1, interval=0.3), row(4, 3, interval=0.7)],
        81: [row(81, 1, interval=0.4), row(81, 3, interval=0.8)],
    }
    samples = field_samples(positions, intervals, [1, 2, 3])
    norris = [s for s in samples if s["driver_number"] == 4]
    assert [s["ahead_driver_number"] for s in norris] == [1, 81, 81]
    assert [s["gap_to_ahead_s"] for s in norris] == [0.3, None, 0.7]
    piastri = [s for s in samples if s["driver_number"] == 81]
    assert piastri[-1]["ahead_driver_number"] == 1
    assert piastri[-1]["gap_to_ahead_s"] == 0.8
    assert not any(s["pressure_eligible"] for s in samples)


@pytest.mark.parametrize("last_rank", [None, 2, 4])
def test_incoherent_full_field_cannot_publish_any_order(last_rank: int | None) -> None:
    positions = {d: [row(d, 0, position=r)] for d, r in ((1, 1), (4, 2), (81, last_rank))}
    samples = field_samples(positions, {1: [], 4: [], 81: []}, [1])
    assert all(s["running_order"] is None for s in samples)
    assert all(s["ahead_driver_number"] is None for s in samples)
    assert all(s["gap_status"] == "unknown_order" for s in samples)


def test_frozen_full_field_retains_austria_exchange() -> None:
    directory = Path("validation/openf1-austria-2025-field")
    manifest, data = load_capture(directory)
    report = json.loads((directory / "evaluation.json").read_text(encoding="utf-8"))
    offset = report["clock_alignment"]["utc_minus_replay_s"]
    samples = field_samples(
        {
            d: [r for r in data["position.json"] if r["driver_number"] == d]
            for d in manifest["drivers"]
        },
        {
            d: [r for r in data["intervals.json"] if r["driver_number"] == d]
            for d in manifest["drivers"]
        },
        [offset + t for t in (821, 822, 834, 835)],
    )
    assert len(samples) == 80
    norris = [s for s in samples if s["driver_number"] == 4]
    assert [s["running_order"] for s in norris] == [1, 2, 2, 1]
    assert norris[1]["gap_to_ahead_s"] == pytest.approx(0.037)
    assert norris[1]["ahead_driver_number"] == 81
