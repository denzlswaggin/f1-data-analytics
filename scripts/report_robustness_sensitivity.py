"""Read-only threshold sensitivity report; not held-out model validation.

Use a pre-v4 snapshot with all two-peer traffic cohorts as the baseline. Traffic
air-state classification and lap inputs are held fixed. Pit grids measure only
extrapolation coverage of fitted models, not reoptimised outcomes or uncertainty.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import pandas as pd
from analytics.traffic import _add_controlled_delta, _match_clean_air_laps, _summarise


def traffic_grid(laps: pd.DataFrame) -> list[dict[str, int]]:
    results = []
    for peers in (2, 3, 5):
        evidence = _match_clean_air_laps(_add_controlled_delta(laps, peers), 2.0)
        for minimum in (5, 8, 12):
            summary = _summarise(
                evidence, min_publish_laps=minimum, traffic_gap_s=1.5, clean_air_gap_s=3.0
            )
            results.append(
                {
                    "minimum_peers": peers,
                    "minimum_publish_laps": minimum,
                    "evidence_laps": len(evidence),
                    "clean_air_results": int(summary.clean_air_eligible.sum()),
                    "association_results": int(summary.traffic_association_eligible.sum()),
                }
            )
    return results


def pit_grid(scenarios: pd.DataFrame) -> list[dict[str, int]]:
    keys = ["season", "round", "driver_code", "stop_number"]
    results = []
    for old_limit in (2, 4, 6):
        for new_limit in (0, 3, 6):
            bounded = scenarios.loc[
                scenarios.old_extrapolation_laps.le(old_limit)
                & scenarios.new_extrapolation_laps.le(new_limit)
            ]
            actual = bounded.loc[bounded.shift_laps.eq(0), keys]
            comparable = bounded.merge(actual, on=keys, validate="many_to_one")
            with_alternative = comparable.groupby(keys).filter(lambda group: len(group) > 1)
            results.append(
                {
                    "max_old_extrapolation_laps": old_limit,
                    "max_new_extrapolation_laps": new_limit,
                    "fitted_stops_with_comparison": len(with_alternative[keys].drop_duplicates()),
                    "bounded_scenarios_including_actual": len(with_alternative),
                }
            )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--current", type=Path, default=Path("data/dashboard/latest.duckdb"))
    args = parser.parse_args()
    with duckdb.connect(str(args.baseline), read_only=True) as connection:
        laps = connection.execute("select * from marts.traffic_adjusted_laps").fetchdf()
    with duckdb.connect(str(args.current), read_only=True) as connection:
        scenarios = connection.execute("select * from marts.pit_timing_scenarios").fetchdf()
    print(
        json.dumps(
            {
                "traffic_fixed_input_threshold_grid": traffic_grid(laps),
                "pit_fitted_model_extrapolation_coverage_only": pit_grid(scenarios),
                "limitations": "Not independent validation; pit grid does not refit models or rank unsupported costs.",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
