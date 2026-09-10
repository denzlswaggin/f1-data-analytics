"""Keep pit timestamps even when no stint or tyre change accompanies a visit."""

from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
from ingestion.clients.fastf1_client import FastF1Client


@pytest.mark.parametrize("has_pit_fields", [True, False])
def test_lap_ingestion_preserves_nullable_session_pit_times(has_pit_fields: bool) -> None:
    laps = pd.DataFrame(
        {
            "Driver": ["RUS"] * 3,
            "DriverNumber": ["63"] * 3,
            "Team": ["Mercedes"] * 3,
            "LapNumber": [61, 62, 63],
            "Stint": [2] * 3,
            "Compound": ["HARD"] * 3,
            "TyreLife": [20, 21, 22],
            "FreshTyre": [False] * 3,
            "Position": [10] * 3,
            "IsPersonalBest": [False] * 3,
            "TrackStatus": ["1"] * 3,
            "LapStartTime": pd.to_timedelta([4000, 4080, 4200], unit="s"),
            "LapTime": pd.to_timedelta([80, 120, 90], unit="s"),
            "Sector1Time": pd.to_timedelta([25, 25, 30], unit="s"),
            "Sector2Time": pd.to_timedelta([30, 30, 30], unit="s"),
            "Sector3Time": pd.to_timedelta([25, 65, 30], unit="s"),
            "SpeedI1": [200] * 3,
            "SpeedI2": [200] * 3,
            "SpeedFL": [200] * 3,
            "SpeedST": [200] * 3,
        }
    )
    if has_pit_fields:
        laps["PitInTime"] = pd.to_timedelta([None, 4180.125, None], unit="s")
        laps["PitOutTime"] = pd.to_timedelta([None, None, 4205.25], unit="s")
    session = SimpleNamespace(laps=laps, load=Mock())
    client = FastF1Client()
    client._fastf1 = SimpleNamespace(get_session=Mock(return_value=session))

    result = client.load_session_laps(2025, 8)

    assert result.stint.tolist() == [2, 2, 2]
    assert result.pit_in_time_sec.dtype == "float64"
    assert result.pit_out_time_sec.dtype == "float64"
    if has_pit_fields:
        assert result.loc[1, "pit_in_time_sec"] == 4180.125
        assert result.loc[2, "pit_out_time_sec"] == 4205.25
        assert result.pit_in_time_sec.isna().tolist() == [True, False, True]
        assert result.pit_out_time_sec.isna().tolist() == [True, True, False]
    else:
        assert result[["pit_in_time_sec", "pit_out_time_sec"]].isna().all().all()
