"""Shared pit-lap exclusions. Absence of observed evidence is never confirmed absence."""

from __future__ import annotations

import pandas as pd

LAP_KEYS = ["season", "round", "driver_code", "lap_number"]
DRIVER_KEYS = LAP_KEYS[:3]
PIT_COLUMNS = [
    "is_pit_in_lap",
    "is_pit_out_lap",
    "is_pit_boundary",
    "pit_context_source",
    "pit_context_status",
    "pit_exclusion_reason",
]


def _empty_context() -> pd.DataFrame:
    return pd.DataFrame(
        {
            **{key: pd.Series(dtype="int64") for key in ("season", "round", "lap_number")},
            "driver_code": pd.Series(dtype="object"),
            **{key: pd.Series(dtype="bool") for key in PIT_COLUMNS[:3]},
            **{key: pd.Series(dtype="object") for key in PIT_COLUMNS[3:]},
        }
    )[LAP_KEYS + PIT_COLUMNS]


def build_pit_lap_context(laps: pd.DataFrame, stops: pd.DataFrame | None = None) -> pd.DataFrame:
    """Union direct timing, pit-stop records and conservative stint boundaries.

    FastF1 timing belongs to the lap carrying the field. Jolpica's pit lap is
    followed by an out-lap, whether or not the tyres/stint changed. An empty stop
    table says nothing about source coverage. Duplicate lap keys are rejected;
    repeated stop records are harmless. Call this before filtering racing laps.
    """
    if laps.empty:
        return _empty_context()
    missing = set(LAP_KEYS) - set(laps.columns)
    if missing:
        raise ValueError(f"Missing lap columns: {sorted(missing)}")
    work = laps.copy()
    if "session" in work:
        work = work.loc[work["session"].eq("R")].copy()
    if work.empty:
        return _empty_context()
    if work[LAP_KEYS].isna().any().any():
        raise ValueError("Pit context lap keys must not be null")
    if work.duplicated(LAP_KEYS).any():
        raise ValueError("Duplicate pit context lap keys")
    work = work.sort_values(LAP_KEYS).reset_index(drop=True)
    inferred_in = pd.Series(False, index=work.index)
    inferred_out = inferred_in.copy()
    stint_known = inferred_in.copy()
    if "stint" in work:
        stint = pd.to_numeric(work["stint"], errors="coerce")
        stint_known = stint.notna()
        work["_stint"] = stint
        groups = work.groupby(DRIVER_KEYS, dropna=False)
        max_stint = groups["_stint"].transform("max")
        stint_groups = work.groupby([*DRIVER_KEYS, "_stint"], dropna=False)
        first_lap = stint_groups["lap_number"].transform("min")
        last_lap = stint_groups["lap_number"].transform("max")
        inferred_in = stint.notna() & stint.lt(max_stint) & work["lap_number"].eq(last_lap)
        # If the feed begins at stint >1, conservatively exclude its first lap.
        inferred_out = stint.gt(1) & work["lap_number"].eq(first_lap)

    fast_in = work.get("pit_in_time_sec", pd.Series(float("nan"), index=work.index)).notna()
    fast_out = work.get("pit_out_time_sec", pd.Series(float("nan"), index=work.index)).notna()
    # Nullable columns alone do not establish coverage: look for observations.
    fast_known = (fast_in | fast_out).groupby([work[key] for key in DRIVER_KEYS]).transform("any")
    jolpica_in = pd.Series(False, index=work.index)
    jolpica_out = jolpica_in.copy()
    jolpica_known = jolpica_in.copy()
    if stops is not None and not stops.empty:
        required = {*DRIVER_KEYS, "pit_lap"}
        missing = required - set(stops.columns)
        if missing:
            raise ValueError(f"Missing stop columns: {sorted(missing)}")
        valid = stops.dropna(subset=[*DRIVER_KEYS, "pit_lap"]).copy()
        valid["pit_lap"] = pd.to_numeric(valid["pit_lap"], errors="coerce")
        valid = valid.loc[valid["pit_lap"].gt(0) & valid["pit_lap"].mod(1).eq(0)]
        lap_index = pd.MultiIndex.from_frame(work[LAP_KEYS])
        pit_keys = valid.rename(columns={"pit_lap": "lap_number"})
        jolpica_in = pd.Series(
            lap_index.isin(pd.MultiIndex.from_frame(pit_keys[LAP_KEYS])), index=work.index
        )
        pit_keys["lap_number"] += 1
        jolpica_out = pd.Series(
            lap_index.isin(pd.MultiIndex.from_frame(pit_keys[LAP_KEYS])), index=work.index
        )
        jolpica_known = pd.Series(
            pd.MultiIndex.from_frame(work[DRIVER_KEYS]).isin(
                pd.MultiIndex.from_frame(valid[DRIVER_KEYS])
            ),
            index=work.index,
        )

    false = pd.Series(False, index=work.index)
    provided_in = work.get("is_pit_in_lap", false).eq(True).fillna(False)
    provided_out = work.get("is_pit_out_lap", false).eq(True).fillna(False)
    provided = (
        work.get("is_pit_boundary", false).eq(True).fillna(False) | provided_in | provided_out
    )
    result = work[LAP_KEYS].copy()
    result["is_pit_in_lap"] = fast_in | jolpica_in | inferred_in | provided_in
    result["is_pit_out_lap"] = fast_out | jolpica_out | inferred_out | provided_out
    result["is_pit_boundary"] = result["is_pit_in_lap"] | result["is_pit_out_lap"] | provided
    result["pit_context_source"] = ""
    for source, evidence in (
        ("fastf1", fast_in | fast_out),
        ("jolpica", jolpica_in | jolpica_out),
        ("stint_inference", inferred_in | inferred_out),
        ("provided_flags", provided),
    ):
        result.loc[evidence, "pit_context_source"] += source + "+"
    result["pit_context_source"] = (
        result["pit_context_source"].str.rstrip("+").replace("", "unavailable")
    )
    known = stint_known | fast_known | jolpica_known
    result["pit_context_status"] = "unknown"
    result.loc[known, "pit_context_status"] = "no_pit_observed"
    result.loc[inferred_in | inferred_out | provided, "pit_context_status"] = "inferred_pit"
    result.loc[fast_in | fast_out | jolpica_in | jolpica_out, "pit_context_status"] = "observed_pit"
    result["pit_exclusion_reason"] = ""
    result.loc[provided, "pit_exclusion_reason"] = "pit_boundary"
    result.loc[result["is_pit_in_lap"], "pit_exclusion_reason"] = "pit_in_lap"
    result.loc[result["is_pit_out_lap"], "pit_exclusion_reason"] = "pit_out_lap"
    result.loc[result["is_pit_in_lap"] & result["is_pit_out_lap"], "pit_exclusion_reason"] = (
        "pit_in_out_lap"
    )
    return result[LAP_KEYS + PIT_COLUMNS]


def attach_pit_lap_context(frame: pd.DataFrame, context: pd.DataFrame) -> pd.DataFrame:
    """Attach many-to-one context, replacing stale exclusions and preserving order."""
    result = frame.drop(columns=PIT_COLUMNS, errors="ignore").merge(
        context[LAP_KEYS + PIT_COLUMNS],
        on=LAP_KEYS,
        how="left",
        validate="many_to_one",
        sort=False,
    )
    for key in PIT_COLUMNS[:3]:
        result[key] = result[key].eq(True)
    for key, default in (
        ("pit_context_source", "unavailable"),
        ("pit_context_status", "unknown"),
        ("pit_exclusion_reason", ""),
    ):
        result[key] = result[key].fillna(default)
    return result
