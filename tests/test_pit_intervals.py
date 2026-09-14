from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from analytics.pit_intervals import observed_pit_intervals


def _laps() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "driver_code": ["A", "A", "B"],
            "lap_start_sec": [1000.0, 1090.0, 995.0],
            "pit_in_time_sec": [1080.0, np.nan, np.nan],
            "pit_out_time_sec": [np.nan, 1100.0, np.nan],
        }
    )


def test_pairs_observed_boundaries_using_full_field_clock() -> None:
    result = observed_pit_intervals(_laps().iloc[::-1])
    assert result.to_dict("records") == [{"driver_code": "A", "entry_t_s": 85.0, "exit_t_s": 105.0}]


def test_unpaired_boundaries_do_not_invent_infinite_intervals() -> None:
    laps = _laps()
    laps.loc[0, "pit_in_time_sec"] = np.nan
    assert observed_pit_intervals(laps).empty
    laps = _laps()
    laps.loc[1, "pit_out_time_sec"] = np.nan
    assert observed_pit_intervals(laps).empty


@pytest.mark.parametrize("failure", ["repeated_entry", "simultaneous", "negative", "infinite"])
def test_invalid_or_ambiguous_boundaries_reject_the_scope(failure: str) -> None:
    laps = _laps()
    if failure == "repeated_entry":
        laps.loc[1, "pit_in_time_sec"] = 1090
    elif failure == "simultaneous":
        laps.loc[1, "pit_out_time_sec"] = 1080
    elif failure == "negative":
        laps.loc[0, "pit_in_time_sec"] = -1
    else:
        laps.loc[0, "pit_in_time_sec"] = np.inf
    with pytest.raises(ValueError):
        observed_pit_intervals(laps)


def test_rejects_mixed_races_and_missing_clock() -> None:
    with pytest.raises(ValueError, match="one race"):
        observed_pit_intervals(_laps().assign(round=[1, 1, 2]))
    with pytest.raises(ValueError, match="clock origin"):
        observed_pit_intervals(_laps().assign(lap_start_sec=np.nan))
