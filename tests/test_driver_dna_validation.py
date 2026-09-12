from __future__ import annotations

import pandas as pd
from analytics.driver_dna import METRICS
from analytics.driver_dna_validation import (
    permutation_negative_control,
    profile_stability,
    tolerance_sensitivity,
)

from tests.test_driver_dna import _laps, _telemetry


def _evidence() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for rnd in range(1, 7):
        for driver, teammate, direction in (("AAA", "BBB", 1), ("BBB", "AAA", -1)):
            row: dict[str, object] = {
                "season": 2025,
                "round": rnd,
                "driver_code": driver,
                "driver_name": f"Driver {driver}",
                "teammate_code": teammate,
                "eligible": True,
            }
            row.update({f"{metric}_z": direction * (0.4 + rnd / 100) for metric in METRICS})
            rows.append(row)
    return pd.DataFrame(rows)


def test_stability_reports_split_and_leave_one_out_diagnostics() -> None:
    result = profile_stability(_evidence())

    assert len(result) == 2 * len(METRICS)
    assert result["stable"].all()
    assert (result["sign_agreement_pct"] == 100).all()
    assert (result["leave_one_out_max_delta"] < 0.1).all()


def test_negative_control_is_deterministic() -> None:
    first = permutation_negative_control(_evidence(), n_permutations=20, seed=42)
    second = permutation_negative_control(_evidence(), n_permutations=20, seed=42)

    pd.testing.assert_frame_equal(first, second)
    assert set(first["metric"]) == set(METRICS)


def test_tolerance_grid_reports_coverage_tradeoff() -> None:
    telemetry = pd.concat([_telemetry("AAA"), _telemetry("BBB")], ignore_index=True)
    result = tolerance_sensitivity(telemetry, _laps())

    assert result["max_lap_gap"].tolist() == [1, 3, 5]
    assert result["eligible_pairs"].tolist() == [0, 1, 1]
