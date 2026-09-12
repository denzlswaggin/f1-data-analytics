from __future__ import annotations

import pandas as pd
import pytest
from analytics.driver_dna import METRICS
from analytics.driver_track import (
    analyse_driver_track,
    build_driver_track_fit,
    classify_circuit_archetypes,
    validate_driver_track,
)


def _microsectors() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for rnd, base_speed, brake in ((1, 250.0, 0.05), (2, 190.0, 0.35), (3, 145.0, 0.15)):
        for segment in range(1, 11):
            for driver, teammate, direction in (("AAA", "BBB", 1), ("BBB", "AAA", -1)):
                rows.append(
                    {
                        "season": 2025,
                        "round": rnd,
                        "race_name": f"Race {rnd}",
                        "driver_code": driver,
                        "driver_name": f"Driver {driver}",
                        "teammate_code": teammate,
                        "segment_number": segment,
                        "segment_delta_sec": direction * rnd / 100,
                        "driver_speed_kph": base_speed + direction,
                        "teammate_speed_kph": base_speed - direction,
                        "driver_brake_share": brake,
                        "teammate_brake_share": brake,
                        "driver_throttle": 100 if rnd == 1 else 80,
                        "teammate_throttle": 100 if rnd == 1 else 80,
                    }
                )
    return pd.DataFrame(rows)


def _evidence() -> pd.DataFrame:
    rows = []
    for rnd in range(1, 7):
        for driver, teammate, direction in (("AAA", "BBB", 1), ("BBB", "AAA", -1)):
            row = {
                "season": 2025,
                "round": rnd,
                "driver_code": driver,
                "driver_name": f"Driver {driver}",
                "teammate_code": teammate,
                "eligible": True,
            }
            row.update({f"{metric}_z": direction * 0.4 for metric in METRICS})
            rows.append(row)
    return pd.DataFrame(rows)


def test_circuit_archetypes_use_each_directed_pair_once() -> None:
    result = classify_circuit_archetypes(_microsectors())

    assert len(result) == 3
    assert set(result["circuit_archetype"]) == {
        "High-speed flow",
        "Heavy braking",
        "Low-speed traction",
    }
    assert result["segments"].tolist() == [10, 10, 10]


def test_driver_fit_keeps_teammate_relative_sign() -> None:
    microsectors = _microsectors()
    archetypes = classify_circuit_archetypes(microsectors)
    fit = build_driver_track_fit(microsectors, archetypes)

    aaa = fit[fit["driver_code"] == "AAA"]
    bbb = fit[fit["driver_code"] == "BBB"]
    assert aaa["median_gain_sec"].sum() == pytest.approx(-bbb["median_gain_sec"].sum())


def test_complete_driver_track_result_validates() -> None:
    result = analyse_driver_track(_evidence(), _microsectors())

    validate_driver_track(result)
    assert len(result.dna_stability) == 2 * len(METRICS)
