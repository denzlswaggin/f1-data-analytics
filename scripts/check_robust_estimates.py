"""Read-only consistency checks for published default robustness policies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb


def check(connection: duckdb.DuckDBPyConnection) -> dict[str, int]:
    queries = {
        "traffic_peer_reconstruction": """with peers as (
                select a.season, a.round, a.driver_code, a.lap_number,
                    count(b.driver_code) as n, median(b.lap_time_sec) as baseline
                from marts.traffic_adjusted_laps a join marts.traffic_adjusted_laps b
                    on a.season = b.season and a.round = b.round
                    and a.lap_number = b.lap_number and a.compound = b.compound
                    and a.driver_code != b.driver_code
                group by a.season, a.round, a.driver_code, a.lap_number
            )
            select count(*) from marts.traffic_adjusted_laps a left join peers b
                using(season, round, driver_code, lap_number)
            where a.peer_count < 3 or a.peer_count is distinct from b.n
                or a.peer_lap_median_sec is null or b.baseline is null
                or abs(a.peer_lap_median_sec - b.baseline) > 0.000001
                or a.controlled_pace_delta_sec is null
                or abs(a.controlled_pace_delta_sec - (a.lap_time_sec - b.baseline)) > 0.000001""",
        "pit_unsupported_publication": """select count(*) from marts.pit_timing_scenarios
            where not supported and (estimated_cost_index_sec is not null
                or delta_vs_actual_sec is not null or estimated_gain_vs_actual_sec is not null
                or delta_p25_sec is not null or delta_p75_sec is not null
                or coalesce(exclusion_reason, '') = '')""",
        "pit_extrapolation_limits": """select count(*) from marts.pit_timing_scenarios p
            join marts.pit_timing_scenarios a using(season, round, driver_code, stop_number)
            where p.supported and a.shift_laps = 0 and
                (not a.supported or p.old_extrapolation_laps is null
                 or p.new_extrapolation_laps is null or p.old_extrapolation_laps > 4
                 or p.new_extrapolation_laps > 3 or a.old_extrapolation_laps > 4
                 or a.new_extrapolation_laps > 3)""",
        "pit_bootstrap_quality": """select count(*) from marts.pit_timing_sensitivity
            where eligible and (bootstrap_valid_samples is null
                or bootstrap_valid_samples < 100
                or bootstrap_valid_samples < 0.9 * bootstrap_requested_samples
                or bootstrap_attempted_samples < bootstrap_valid_samples
                or bootstrap_valid_samples > bootstrap_requested_samples
                or best_shift_win_pct is null or best_shift_win_pct not between 0 and 100)
                or (confidence = 'high' and (boundary_minimum or bootstrap_valid_samples < 300))""",
        "pit_summary_scenarios": """with evidence as (
                select season, round, driver_code, stop_number, count(*) as total,
                    count(*) filter(where supported) as n,
                    count(*) filter(where supported and shift_laps = 0) as actual,
                    min(shift_laps) filter(where supported) as low,
                    max(shift_laps) filter(where supported) as high
                from marts.pit_timing_scenarios group by all
            )
            select count(*) from marts.pit_timing_sensitivity s
            left join evidence e using(season, round, driver_code, stop_number)
            left join marts.pit_timing_scenarios b
                on s.season = b.season and s.round = b.round and s.driver_code = b.driver_code
                and s.stop_number = b.stop_number and b.shift_laps = s.best_supported_shift_laps
            where e.total is distinct from 7 or s.supported_scenarios is distinct from e.n
                or (s.eligible and (e.n < 2 or e.actual != 1 or b.supported is distinct from true
                    or s.estimated_gain_vs_actual_sec is distinct from b.estimated_gain_vs_actual_sec
                    or s.boundary_minimum is distinct from
                        (s.best_supported_shift_laps != 0
                         and s.best_supported_shift_laps in (e.low, e.high))))""",
    }
    result = {}
    for name, query in queries.items():
        row = connection.execute(query).fetchone()
        assert row is not None
        result[name] = int(row[0])
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, nargs="?", default=Path("data/dashboard/latest.duckdb"))
    args = parser.parse_args()
    with duckdb.connect(str(args.path), read_only=True) as connection:
        violations = check(connection)
    print(json.dumps(violations, indent=2, sort_keys=True))
    if any(violations.values()):
        raise SystemExit("FAIL: robustness publication rules are inconsistent")
    print("PASS: robust peers, extrapolation, resampling and scenario publication")


if __name__ == "__main__":
    main()
