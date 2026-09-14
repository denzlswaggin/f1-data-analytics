"""Recover missing observed pit timestamps without silently replacing lap data."""

from __future__ import annotations

import numpy as np
import pandas as pd

KEYS = ["season", "round", "session", "driver_code", "lap_number"]
TIMESTAMPS = ["pit_in_time_sec", "pit_out_time_sec"]


def recover_pit_timestamps(existing: pd.DataFrame, recovered: pd.DataFrame) -> pd.DataFrame:
    """Require identical scope, driver identity, lap clocks and stint metadata.

    Only missing pit timestamps can be filled. Conflicting existing observations
    or changed lap inputs require a separate reconciliation, not an automatic
    backfill. Microsecond tolerance handles floating-point storage, not a shifted
    session clock. Original row order, keys and all other fields are preserved.
    """
    numeric = ["lap_start_sec", "lap_time_sec", "stint", "tyre_life"]
    identities = ["driver_number", "compound"]
    required = set(KEYS + numeric + identities + TIMESTAMPS)
    for frame in (existing, recovered):
        if required - set(frame):
            raise ValueError(f"Missing recovery fields: {sorted(required - set(frame))}")
        if frame[KEYS].isna().any().any() or frame.duplicated(KEYS).any():
            raise ValueError("Recovery requires unique, non-null lap keys")
    aligned = existing[KEYS].merge(
        recovered, on=KEYS, how="outer", indicator=True, validate="one_to_one", sort=False
    )
    if not aligned["_merge"].eq("both").all():
        raise ValueError("Recovered lap scope differs from existing data")
    # An explicit merge back to the original index order avoids relying on the
    # ordering of an outer join.
    donor = existing[KEYS].merge(recovered, on=KEYS, how="left", validate="one_to_one", sort=False)
    old = existing.reset_index(drop=True)
    for name in numeric:
        a = pd.to_numeric(old[name], errors="raise").to_numpy(dtype=float, na_value=np.nan)
        b = pd.to_numeric(donor[name], errors="raise").to_numpy(dtype=float, na_value=np.nan)
        if not np.isclose(a, b, atol=1e-6, rtol=0, equal_nan=True).all():
            raise ValueError(f"Recovered lap input changed: {name}")
    for name in identities:
        left = old[name].astype("string")
        right = donor[name].astype("string")
        if name == "compound":
            # Match stg_laps.sql's documented raw-to-staging normalization.
            # This equates missing markers, never two different known tyres.
            left = left.str.strip().str.upper().fillna("UNKNOWN")
            right = right.str.strip().str.upper().fillna("UNKNOWN")
            left = left.replace({"": "UNKNOWN", "NONE": "UNKNOWN", "NAN": "UNKNOWN"})
            right = right.replace({"": "UNKNOWN", "NONE": "UNKNOWN", "NAN": "UNKNOWN"})
        if not left.fillna("<missing>").equals(right.fillna("<missing>")):
            raise ValueError(f"Recovered driver/stint identity changed: {name}")
    result = old.copy()
    for name in TIMESTAMPS:
        a = pd.to_numeric(old[name], errors="raise").to_numpy(dtype=float, na_value=np.nan)
        b = pd.to_numeric(donor[name], errors="raise").to_numpy(dtype=float, na_value=np.nan)
        if np.any(~np.isnan(b) & (~np.isfinite(b) | (b < 0))):
            raise ValueError(f"Invalid recovered timestamp: {name}")
        known = ~np.isnan(a)
        if not np.isclose(a[known], b[known], atol=1e-6, rtol=0, equal_nan=True).all():
            raise ValueError(f"Conflicting observed timestamp: {name}")
        result[name] = np.where(known, a, b)
    result.index = existing.index
    return result
