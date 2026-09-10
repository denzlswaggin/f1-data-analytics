"""Read-only default-threshold traffic/tyre publication checks for package 4."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb


def check(connection: duckdb.DuckDBPyConnection) -> dict[str, int]:
    queries = {
        "traffic_eligibility": """select count(*) from marts.traffic_adjusted_pace
            where clean_air_eligible is distinct from (clean_air_laps >= 5)
                or traffic_association_eligible is distinct from
                    (clean_air_laps >= 5 and matched_traffic_laps >= 5)
                or clean_air_eligible is distinct from (traffic_adjusted_pace_delta_sec is not null)
                or traffic_association_eligible is distinct from
                    (traffic_associated_delta_sec_per_lap is not null)""",
        "traffic_sample_strength": """select count(*) from marts.traffic_adjusted_pace
            where clean_air_confidence is distinct from case
                    when clean_air_laps >= 12 then 'high' when clean_air_laps >= 8 then 'medium'
                    when clean_air_laps >= 5 then 'low' else 'insufficient' end
                or traffic_association_confidence is distinct from case
                    when least(clean_air_laps, matched_traffic_laps) >= 12 then 'high'
                    when least(clean_air_laps, matched_traffic_laps) >= 8 then 'medium'
                    when least(clean_air_laps, matched_traffic_laps) >= 5 then 'low'
                    else 'insufficient' end
                or confidence is distinct from traffic_association_confidence""",
        "tyre_exact_publication": """select count(*) from marts.tyre_warmup
            where time_to_pace_laps is distinct from case when confirmation_history_complete
                    then first_observed_confirmation_laps else null end
                or crossover_eligible is distinct from
                    (confirmation_history_complete or right_censored)
                or stable_pace_achieved is distinct from
                    (first_observed_confirmation_laps is not null)
                or right_censored is distinct from
                    (warmup_eligible and not stable_pace_achieved and observation_complete)""",
        "tyre_status": """select count(*) from marts.tyre_warmup
            where settling_status is distinct from case
                when confirmation_history_complete then 'observed_complete'
                when stable_pace_achieved then 'observed_incomplete'
                when right_censored then 'right_censored'
                when warmup_eligible then 'incomplete' else 'unavailable' end""",
        "tyre_history_evidence": """with evidence as (
                select s.season, s.round, s.driver_code, s.stint,
                    count(distinct l.post_stop_offset) filter (where l.lap_eligible
                        and l.post_stop_offset between 1 and 6) as window_count,
                    count(distinct l.post_stop_offset) filter (where l.lap_eligible
                        and l.post_stop_offset between 1 and s.first_observed_confirmation_laps)
                        as history_count
                from marts.tyre_warmup s left join marts.tyre_warmup_laps l
                    using(season, round, driver_code, stint)
                group by s.season, s.round, s.driver_code, s.stint
            )
            select count(*) from marts.tyre_warmup s join evidence e
                using(season, round, driver_code, stint)
            where s.observation_complete is distinct from (s.warmup_eligible and e.window_count = 6)
                or s.confirmation_history_complete is distinct from
                    (s.first_observed_confirmation_laps is not null
                     and e.history_count = s.first_observed_confirmation_laps)""",
        "tyre_first_observed_pair": """with pairs as (
                select a.season, a.round, a.driver_code, a.stint,
                    min(b.post_stop_offset) as first_confirmation
                from marts.tyre_warmup_laps a join marts.tyre_warmup_laps b
                    on a.season = b.season and a.round = b.round
                    and a.driver_code = b.driver_code and a.stint = b.stint
                    and b.post_stop_offset = a.post_stop_offset + 1
                where a.lap_eligible and b.lap_eligible
                    and a.within_stable_band and b.within_stable_band
                    and a.post_stop_offset between 1 and 5
                group by a.season, a.round, a.driver_code, a.stint
            )
            select count(*) from marts.tyre_warmup s left join pairs p
                using(season, round, driver_code, stint)
            where s.first_observed_confirmation_laps is distinct from p.first_confirmation""",
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
        raise SystemExit("FAIL: metric evidence publication is inconsistent")
    print("PASS: metric-specific sample strength and tyre observation semantics")


if __name__ == "__main__":
    main()
