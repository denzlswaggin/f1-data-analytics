from __future__ import annotations

import pandas as pd
from ingestion.pipeline import _openf1_clock_audit, _openf1_digest, _openf1_gap


def test_openf1_gap_keeps_numeric_and_lap_deficit_separate() -> None:
    assert _openf1_gap(1.234) == (1.234, None)
    assert _openf1_gap("+1 LAP") == (None, 1)
    assert _openf1_gap("+2 LAPS") == (None, 2)
    assert _openf1_gap(None) == (None, None)
    assert _openf1_gap(-1) == (None, None)


def test_openf1_digest_is_order_stable_for_object_keys() -> None:
    assert _openf1_digest([{"b": 2, "a": 1}]) == _openf1_digest([{"a": 1, "b": 2}])


def test_clock_audit_accepts_many_consistent_anchors_and_one_red_flag_outlier() -> None:
    t0 = pd.Timestamp("2026-09-06T12:00:00Z")
    codes = {str(number): f"D{number}" for number in range(1, 5)}
    local_rows = []
    source_rows = []
    for number, code in codes.items():
        for lap in range(1, 4):
            local_second = 100.0 + 90.0 * (lap - 1) + int(number) / 10
            local_rows.append(
                {"driver_code": code, "lap_number": lap, "lap_start_sec": local_second}
            )
            source_second = local_second + (1800.0 if number == "4" and lap == 3 else 0.2)
            source_rows.append(
                {
                    "driver_number": int(number),
                    "lap_number": lap,
                    "date_start": (t0 + pd.Timedelta(source_second, unit="s")).isoformat(),
                }
            )

    result = _openf1_clock_audit(source_rows, pd.DataFrame(local_rows), t0, codes)

    assert result["status"] == "verified"
    assert result["anchor_count"] == 12
    assert result["inlier_anchor_count"] == 11
    assert result["anchor_driver_count"] == 4
    assert 0.19 <= float(result["alignment_p95_s"]) <= 0.21


def test_clock_audit_rejects_insufficient_driver_coverage() -> None:
    result = _openf1_clock_audit(
        [
            {
                "driver_number": 1,
                "lap_number": lap,
                "date_start": f"2026-01-01T00:{lap:02d}:00Z",
            }
            for lap in range(1, 9)
        ],
        pd.DataFrame(
            [
                {"driver_code": "A", "lap_number": lap, "lap_start_sec": lap * 60.0}
                for lap in range(1, 9)
            ]
        ),
        pd.Timestamp("2026-01-01T00:00:00Z"),
        {"1": "A"},
    )

    assert result["status"] == "rejected"
    assert result["anchor_driver_count"] == 1
