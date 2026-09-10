"""Read-only cross-mart checks for the shared pit mask in a built snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, nargs="?", default=Path("data/dashboard/latest.duckdb"))
    args = parser.parse_args()
    violations: dict[str, int] = {}
    with duckdb.connect(str(args.path), read_only=True) as connection:
        for table, eligible in (
            ("traffic_adjusted_laps", "true"),
            ("pace_consistency_laps", "lap_eligible"),
            ("tyre_warmup_laps", "lap_eligible or used_for_baseline"),
        ):
            count = connection.execute(
                f"select count(*) from marts.{table} "
                "join marts.pit_lap_context using (season, round, driver_code, lap_number) "
                f"where is_pit_boundary and ({eligible})"
            ).fetchone()
            assert count is not None
            violations[table] = int(count[0])
        count = connection.execute(
            "select count(*) from (select season, round, driver_code, lap_number "
            "from marts.pit_lap_context group by all having count(*) > 1)"
        ).fetchone()
        assert count is not None
        violations["duplicate_context_keys"] = int(count[0])
        for table in ("traffic_adjusted_laps", "pace_consistency_laps", "tyre_warmup_laps"):
            count = connection.execute(
                f"select count(*) from marts.{table} evidence "
                "left join marts.pit_lap_context context "
                "using (season, round, driver_code, lap_number) "
                "where context.lap_number is null"
            ).fetchone()
            assert count is not None
            violations[f"{table}_missing_context"] = int(count[0])
    print(json.dumps(violations, indent=2, sort_keys=True))
    if any(violations.values()):
        raise SystemExit("FAIL: shared pit context is inconsistent with analytical evidence")
    print("PASS: shared pit exclusions and lap-key coverage")


if __name__ == "__main__":
    main()
