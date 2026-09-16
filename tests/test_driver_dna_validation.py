from __future__ import annotations

import pandas as pd
from analytics.driver_dna import METRICS
from analytics.driver_dna_validation import (
    build_stability_windows,
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
    assert set(result["from_season"]) == {2025}
    assert set(result["to_season"]) == {2025}
    assert result["stable"].all()
    assert (result["sign_agreement_pct"] == 100).all()
    assert (result["leave_one_out_max_delta"] < 0.1).all()


def test_stability_windows_match_every_contiguous_available_season_scope() -> None:
    evidence = pd.concat(
        [
            _evidence().assign(season=2024),
            _evidence(),
            _evidence().assign(season=2026),
        ],
        ignore_index=True,
    )

    result = build_stability_windows(evidence)

    assert set(zip(result["from_season"], result["to_season"], strict=True)) == {
        (2024, 2024),
        (2024, 2025),
        (2024, 2026),
        (2025, 2025),
        (2025, 2026),
        (2026, 2026),
    }
    assert len(result) == 6 * 2 * len(METRICS)


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
