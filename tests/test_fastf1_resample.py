"""Offline test for the pure telemetry-resampling helper (no FastF1 needed)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from ingestion.clients.fastf1_client import (
    clean_positions,
    resample_lap_telemetry,
    thin_positions,
)


def _synthetic_lap() -> pd.DataFrame:
    dist = np.linspace(0, 1000, 51)
    return pd.DataFrame(
        {
            "Distance": dist,
            "Speed": np.linspace(100, 300, 51),
            "Throttle": np.linspace(0, 100, 51),
            "RPM": np.linspace(9000, 12000, 51),
            "X": dist,  # straight line so interpolation is trivial to check
            "Y": np.zeros(51),
            "Brake": np.zeros(51),
            "DRS": np.zeros(51),
            "nGear": np.linspace(2, 8, 51),
        }
    )


def test_resample_grid_spacing_and_columns() -> None:
    out = resample_lap_telemetry(_synthetic_lap(), step_m=25.0)
    # Grid is 0, 25, ... up to but excluding 1000 -> 40 points.
    assert list(out["distance_m"][:3]) == [0.0, 25.0, 50.0]
    assert len(out) == 40
    assert set(out.columns) == {
        "distance_m",
        "speed_kph",
        "throttle",
        "rpm",
        "x",
        "y",
        "brake",
        "drs",
        "gear",
    }
    # Discrete channels are integer-typed.
    assert out["gear"].dtype == "int64"
    # Linear interpolation recovers the straight-line X = distance.
    np.testing.assert_allclose(out["x"].to_numpy(), out["distance_m"].to_numpy())


def test_resample_empty_without_distance() -> None:
    assert resample_lap_telemetry(pd.DataFrame({"Speed": [1, 2]}), 25.0).empty
    assert resample_lap_telemetry(pd.DataFrame(), 25.0).empty


def test_thin_positions_caps_rate_and_sorts() -> None:
    # 10 Hz input (0.1 s spacing), thinned to 5 Hz -> keep one per 0.2 s bucket.
    t = np.round(np.arange(0.0, 1.0, 0.1), 1)
    df = pd.DataFrame({"session_time_sec": t[::-1], "x": t[::-1], "y": np.zeros_like(t)})
    out = thin_positions(df, rate_hz=5.0)
    # Output is time-sorted ascending.
    assert list(out["session_time_sec"]) == sorted(out["session_time_sec"])
    # First sample of each 0.2 s bucket: 0.0, 0.2, 0.4, 0.6, 0.8.
    np.testing.assert_allclose(out["session_time_sec"].to_numpy(), [0.0, 0.2, 0.4, 0.6, 0.8])


def test_thin_positions_drops_nonfinite_and_handles_empty() -> None:
    df = pd.DataFrame({"session_time_sec": [0.0, np.nan, 0.5], "x": [1.0, 2.0, 3.0]})
    out = thin_positions(df, rate_hz=100.0)  # high cap = keep all finite rows
    assert list(out["session_time_sec"]) == [0.0, 0.5]
    assert thin_positions(pd.DataFrame(), rate_hz=5.0).empty


def test_clean_positions_drops_sentinels_and_teleports() -> None:
    # Times chosen so a teleport (>300 m/s at unit_per_m=10 => >3000 units/s) is the
    # only impossible move; a big jump over a long gap stays (low implied speed).
    df = pd.DataFrame(
        {
            "session_time_sec": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 5.0, 5.2],
            "x": [1000.0, 1100.0, 0.0, 1200.0, 50000.0, 1300.0, 2000.0, 2000.0],
            "y": [1000.0, 1000.0, 0.0, 1000.0, 1000.0, 1000.0, 1000.0, 1000.0],
        }
    )
    out = clean_positions(df, max_speed_mps=300.0)
    # (0,0) sentinel (t=0.4) and the teleport (t=0.8) are gone; everything else stays,
    # including the stationary point (t=5.2) and the far-but-slow gap point (t=5.0).
    assert list(out["session_time_sec"]) == [0.0, 0.2, 0.6, 1.0, 5.0, 5.2]
    assert not ((out["x"] == 0) & (out["y"] == 0)).any()
    assert 50000.0 not in set(out["x"])


def test_clean_positions_handles_empty_and_all_sentinel() -> None:
    assert clean_positions(pd.DataFrame(columns=["session_time_sec", "x", "y"]), 300.0).empty
    allzero = pd.DataFrame({"session_time_sec": [0.0, 0.2], "x": [0.0, 0.0], "y": [0.0, 0.0]})
    assert clean_positions(allzero, 300.0).empty
