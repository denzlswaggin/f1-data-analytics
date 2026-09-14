import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from analytics.pit_recovery import recover_pit_timestamps


def laps() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "season": [2025, 2025],
            "round": [11, 11],
            "session": ["R", "R"],
            "driver_code": ["NOR", "NOR"],
            "driver_number": ["4", "4"],
            "lap_number": [20, 21],
            "lap_start_sec": [5000.0, 5090.0],
            "lap_time_sec": [90.0, 100.0],
            "stint": [1, 2],
            "tyre_life": [20, 1],
            "compound": ["MEDIUM", "HARD"],
            "pit_in_time_sec": [np.nan, np.nan],
            "pit_out_time_sec": [np.nan, np.nan],
        },
        index=[10, 20],
    )


def test_recovery_only_fills_timestamps_and_preserves_original_order() -> None:
    original = laps()
    donor = original.copy()
    donor.loc[10, "pit_in_time_sec"] = 5080
    donor.loc[20, "pit_out_time_sec"] = 5105
    result = recover_pit_timestamps(original, donor.iloc[::-1])
    pd.testing.assert_frame_equal(
        result.drop(columns=["pit_in_time_sec", "pit_out_time_sec"]),
        original.drop(columns=["pit_in_time_sec", "pit_out_time_sec"]),
    )
    assert result.loc[10, "pit_in_time_sec"] == 5080
    assert result.loc[20, "pit_out_time_sec"] == 5105
    assert original.pit_in_time_sec.isna().all()


@pytest.mark.parametrize(
    "column,value",
    [
        ("lap_start_sec", 5001),
        ("lap_time_sec", 89),
        ("stint", 2),
        ("driver_number", "81"),
        ("compound", "SOFT"),
    ],
)
def test_changed_identity_or_clock_blocks_recovery(column: str, value: object) -> None:
    original = laps()
    donor = original.copy()
    donor.loc[10, column] = value
    with pytest.raises(ValueError, match="changed"):
        recover_pit_timestamps(original, donor)


def test_missing_laps_and_conflicting_observations_are_rejected() -> None:
    original = laps()
    with pytest.raises(ValueError, match="scope"):
        recover_pit_timestamps(original, original.iloc[:1])
    donor = original.copy()
    original.loc[10, "pit_in_time_sec"] = 5080
    donor.loc[10, "pit_in_time_sec"] = 5081
    with pytest.raises(ValueError, match="Conflicting"):
        recover_pit_timestamps(original, donor)


@pytest.mark.parametrize("value", [-1.0, np.inf, -np.inf])
def test_invalid_timestamp_is_rejected(value: float) -> None:
    donor = laps()
    donor.loc[10, "pit_in_time_sec"] = value
    with pytest.raises(ValueError, match="Invalid"):
        recover_pit_timestamps(laps(), donor)


def test_duplicate_or_missing_keys_are_rejected() -> None:
    donor = laps()
    with pytest.raises(ValueError, match="unique"):
        recover_pit_timestamps(laps(), pd.concat([donor, donor.iloc[:1]]))
    donor.loc[10, "driver_code"] = None
    with pytest.raises(ValueError, match="non-null"):
        recover_pit_timestamps(laps(), donor)


def test_staging_unknown_compound_matches_missing_source_without_replacing_it() -> None:
    original = laps()
    original.loc[10, "compound"] = "UNKNOWN"
    donor = original.copy()
    donor.loc[10, "compound"] = None
    donor.loc[10, "pit_in_time_sec"] = 5080
    result = recover_pit_timestamps(original, donor)
    assert result.loc[10, "compound"] == "UNKNOWN"
    assert result.loc[10, "pit_in_time_sec"] == 5080


def test_frozen_all_race_recovery_preserves_source_hashes_and_reproduces_candidates() -> None:
    root = Path(__file__).resolve().parents[1] / "validation/pit-recovery-20260914"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["complete"] and len(manifest["races"]) == 60
    assert (
        hashlib.sha256((root / "initial-manifest.json").read_bytes()).hexdigest()
        == manifest["source_capture_sha256"]
    )
    for race in manifest["races"]:
        assert race["status"] == "reconciled"
        for kind in ("source", "candidate"):
            assert (
                hashlib.sha256((root / race[f"{kind}_file"]).read_bytes()).hexdigest()
                == race[f"{kind}_sha256"]
            )
        donor = pd.read_parquet(root / race["source_file"])
        candidate = pd.read_parquet(root / race["candidate_file"])
        baseline = candidate.copy()
        baseline[["pit_in_time_sec", "pit_out_time_sec"]] = np.nan
        actual = recover_pit_timestamps(baseline, donor)
        pd.testing.assert_frame_equal(actual, candidate)
