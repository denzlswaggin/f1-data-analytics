"""Pair observed pit boundaries on the replay clock without inventing endpoints."""

from __future__ import annotations

from itertools import pairwise

import numpy as np
import pandas as pd


def observed_pit_intervals(laps: pd.DataFrame) -> pd.DataFrame:
    """Return complete entry/exit pairs from one race's unfiltered lap scope.

    FastF1 pit times use the session clock. Replay subtracts the minimum lap
    start across the full field. Missing initial entries/final exits remain
    unpaired; they never become infinite intervals or evidence of a clear track.
    Nonalternating or simultaneous boundaries are ambiguous and fail closed.
    """
    required = {"driver_code", "lap_start_sec", "pit_in_time_sec", "pit_out_time_sec"}
    if missing := required - set(laps):
        raise ValueError(f"Pit interval laps missing columns: {sorted(missing)}")
    work = laps.loc[laps.session.eq("R")] if "session" in laps else laps
    for scope in ("season", "round"):
        if scope in work and work[scope].nunique(dropna=False) > 1:
            raise ValueError("Pit intervals require exactly one race scope")
    result = pd.DataFrame(
        {
            "driver_code": pd.Series(dtype="string"),
            "entry_t_s": pd.Series(dtype="float64"),
            "exit_t_s": pd.Series(dtype="float64"),
        }
    )
    if work.empty:
        return result
    if work.driver_code.isna().any():
        raise ValueError("Pit interval driver identity is missing")
    values = work[["lap_start_sec", "pit_in_time_sec", "pit_out_time_sec"]].apply(
        pd.to_numeric, errors="raise"
    )
    if (~np.isfinite(values) & values.notna()).any().any():
        raise ValueError("Nonfinite pit clock observation")
    origin = values.lap_start_sec.min()
    if not np.isfinite(origin):
        raise ValueError("Pit intervals require a finite replay clock origin")
    rows = []
    for driver, group in work.assign(**{name: values[name] for name in values}).groupby(
        "driver_code", sort=True
    ):
        events = sorted(
            (float(value), kind)
            for kind, name in (("in", "pit_in_time_sec"), ("out", "pit_out_time_sec"))
            for value in group[name].dropna()
        )
        if any(time < 0 for time, _ in events):
            raise ValueError("Negative session pit timestamp")
        for previous, current in pairwise(events):
            if previous[0] == current[0] or previous[1] == current[1]:
                raise ValueError(f"Ambiguous pit boundary sequence for {driver}")
            if previous[1] == "in":
                rows.append((str(driver), previous[0] - origin, current[0] - origin))
    if not rows:
        return result
    return pd.DataFrame(rows, columns=list(result)).astype({"driver_code": "string"})
