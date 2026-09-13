"""Read-only publication checks for default-threshold racecraft v3 snapshots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, nargs="?", default=Path("data/dashboard/latest.duckdb"))
    args = parser.parse_args()
    queries = {
        "missing_driver_summaries": """select count(*) from (
                select distinct season, round, driver_code from marts.race_replay
                where driver_code is not null and running_order is not null
                    and t_s is not null and isfinite(t_s)
                except select season, round, driver_code from marts.racecraft_driver_summary
            ) expected""",
        "duplicate_driver_summaries": """select count(*) from (
                select season, round, driver_code from marts.racecraft_driver_summary
                group by all having count(*) > 1
            ) duplicates""",
        "duplicate_episode_ids": """select count(*) from (
                select season, round, battle_id from marts.racecraft_battles
                group by all having count(*) > 1
            ) duplicates""",
        "invalid_pressure_runs": """select count(*) from marts.racecraft_battles
            where longest_pressure_run_s is null or longest_pressure_run_s < 0
                or longest_pressure_run_s > pressure_seconds + 0.000001
                or (eligible and longest_pressure_run_s < minimum_pressure_s)""",
        "unconfirmed_defences": """select count(*) from marts.racecraft_battles
            where outcome = 'Defended' and
                (release_run_s is null or release_run_s < 15 or not defender_retained)""",
        "invalid_high_confidence": """select count(*) from marts.racecraft_battles
            where confidence = 'high' and (not eligible or longest_pressure_run_s < 20)""",
        "invalid_eligible_outcomes": """select count(*) from marts.racecraft_battles
            where eligible and outcome not in ('Converted', 'Defended')""",
        "incorrect_reversal_ownership": """with evidence as (
                select season, round, defender_code as driver_code, 1 as made, 0 as conceded
                from marts.racecraft_battles where quick_reversal
                union all
                select season, round, attacker_code, 0, 1
                from marts.racecraft_battles where quick_reversal
            ), expected as (
                select season, round, driver_code, sum(made) as made, sum(conceded) as conceded
                from evidence group by all
            )
            select count(*) from marts.racecraft_driver_summary s
            full outer join expected e using(season, round, driver_code)
            where s.driver_code is null
                or s.quick_reversals_made is distinct from coalesce(e.made, 0)
                or s.quick_reversals_conceded is distinct from coalesce(e.conceded, 0)""",
        "incorrect_summary_denominators": """with evidence as (
                select season, round, attacker_code as driver_code, 1 as attacks, 0 as defences,
                    converted::int as converted, 0 as held
                from marts.racecraft_battles where eligible
                union all
                select season, round, defender_code, 0, 1, 0, defender_retained::int
                from marts.racecraft_battles where eligible
            ), expected as (
                select season, round, driver_code, sum(attacks) as attacks,
                    sum(defences) as defences, sum(converted) as converted, sum(held) as held
                from evidence group by all
            )
            select count(*) from marts.racecraft_driver_summary s
            full outer join expected e using(season, round, driver_code)
            where s.driver_code is null
                or s.attacking_opportunities is distinct from coalesce(e.attacks, 0)
                or s.defensive_opportunities is distinct from coalesce(e.defences, 0)
                or s.converted_opportunities is distinct from coalesce(e.converted, 0)
                or s.defences_held is distinct from coalesce(e.held, 0)""",
    }
    with duckdb.connect(str(args.path), read_only=True) as connection:
        violations = {}
        for name, query in queries.items():
            row = connection.execute(query).fetchone()
            assert row is not None
            violations[name] = int(row[0])
    print(json.dumps(violations, indent=2, sort_keys=True))
    if any(violations.values()):
        raise SystemExit("FAIL: racecraft publication rules are inconsistent")
    print("PASS: racecraft pressure, release, reversals and summary denominators")


if __name__ == "__main__":
    main()
