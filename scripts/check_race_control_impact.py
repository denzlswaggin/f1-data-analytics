"""Read-only publication and cohort checks for race-control v2 snapshots."""

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
        "unclean_eligible_events": "select count(*) from marts.race_control_events where eligible and not recovery_clean",
        "undersized_published_cohorts": "select count(*) from marts.race_control_events where time_eligible and time_comparable_driver_count < 5",
        "invalid_time_publication": """select count(*) from marts.race_control_impact
            where (field_adjusted_gap_gain_s is not null) != time_eligible
                or (time_eligible and (not eligible or event_type = 'Red Flag'
                    or lap_deficit_changed is distinct from false
                    or lap_deficit_before is null or lap_deficit_after is null
                    or time_comparable_driver_count < 5))""",
        "missing_time_exclusion_reason": "select count(*) from marts.race_control_impact where not time_eligible and coalesce(time_exclusion_reason, '') = ''",
        "event_driver_cohort_disagreement": """select count(*) from marts.race_control_impact d
            join marts.race_control_events e using(event_id)
            where d.time_comparable_driver_count != e.time_comparable_driver_count
                or (d.time_eligible and not e.time_eligible)""",
        "incorrect_centering": """select count(*) from (
            select field_adjusted_gap_gain_s, raw_gap_gain_s,
                median(raw_gap_gain_s) over(partition by event_id) as centre
            from marts.race_control_impact where time_eligible
        ) where abs(field_adjusted_gap_gain_s - (raw_gap_gain_s - centre)) > 0.000001""",
    }
    with duckdb.connect(str(args.path), read_only=True) as connection:
        violations = {}
        for name, query in queries.items():
            row = connection.execute(query).fetchone()
            assert row is not None
            violations[name] = int(row[0])
    print(json.dumps(violations, indent=2, sort_keys=True))
    if any(violations.values()):
        raise SystemExit("FAIL: race-control publication rules are inconsistent")
    print("PASS: race-control time cohorts, recovery and centering")


if __name__ == "__main__":
    main()
