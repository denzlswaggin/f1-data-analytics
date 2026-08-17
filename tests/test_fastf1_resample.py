"""Offline test for the pure telemetry-resampling helper (no FastF1 needed)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from ingestion.clients.fastf1_client import resample_lap_telemetry, thin_positions


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
