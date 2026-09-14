"""Recompute traffic evidence from a published snapshot without modifying it."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import duckdb
from analytics.pit_context import attach_pit_lap_context
from analytics.traffic import analyse_traffic_adjusted_pace


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.report is not None and args.report.exists():
        parser.error("Use a new report path to preserve previous evidence")
    baseline_hash = digest(args.snapshot)
    implementation = Path(__file__).resolve().parents[1] / "analytics/traffic.py"
    implementation_hash = hashlib.sha256(
        implementation.read_text(encoding="utf-8").encode("utf-8")
    ).hexdigest()
    tables = {}
    with duckdb.connect(str(args.snapshot), read_only=True) as connection:
        laps = connection.sql("select * from marts.mart_lap_times").df()
        context = connection.sql("select * from marts.pit_lap_context").df()
        replay = connection.sql("select * from marts.race_replay").df()
        result = analyse_traffic_adjusted_pace(attach_pit_lap_context(laps, context), replay)

        def count(sql: str) -> int:
            row = connection.sql(sql).fetchone()
            assert row is not None
            return int(row[0])

        for table, frame in (
            ("traffic_adjusted_laps", result.evidence),
            ("traffic_adjusted_pace", result.summary),
        ):
            connection.register("recomputed", frame)
            tables[table] = {
                "rows": len(frame),
                "removed": count(
                    f"select count(*) from (select * from marts.{table} "
                    "except all select * from recomputed)"
                ),
                "added": count(
                    "select count(*) from (select * from recomputed "
                    f"except all select * from marts.{table})"
                ),
            }
            connection.unregister("recomputed")
    if digest(args.snapshot) != baseline_hash:
        raise ValueError("Snapshot changed during verification")
    if (
        hashlib.sha256(implementation.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
        != implementation_hash
    ):
        raise ValueError("Traffic implementation changed during verification")
    report = {
        "baseline_sha256": baseline_hash,
        "traffic_implementation_sha256": implementation_hash,
        "tables": tables,
    }
    text = json.dumps(report, indent=2) + "\n"
    print(text)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
    if any(table["removed"] or table["added"] for table in tables.values()):
        raise SystemExit("FAIL: recomputed traffic outputs differ from the published snapshot")


if __name__ == "__main__":
    main()
