"""Offline test for the pure telemetry-resampling helper (no FastF1 needed)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from ingestion.clients.fastf1_client import resample_lap_telemetry


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
