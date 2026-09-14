"""Create an isolated candidate correcting classification from preserved source text."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import duckdb
from ingestion.dashboard_snapshot import validate_dashboard_snapshot


def migrate(source: Path, output: Path, report: Path) -> None:
    if output.exists() or report.exists():
        raise FileExistsError("Candidate and audit paths must be new")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, output)
    with duckdb.connect(str(output)) as conn:
        conn.execute("""
            create temporary table corrections as
            select season, round, driver_code, finish_position, position_text, status,
                is_classified as previous_is_classified,
                case when finish_position > 0
                    and trim(position_text) = cast(finish_position as varchar) then true
                    when trim(position_text) in ('R', 'D', 'W', 'F') then false
                    else null end as source_is_classified
            from staging.stg_results
        """)
        changed = conn.sql("""
            select * from corrections
            where previous_is_classified is distinct from source_is_classified
            order by season, round, driver_code
        """).fetchdf()
        conn.execute("""
            update staging.stg_results r set is_classified = c.source_is_classified
            from corrections c
            where r.season=c.season and r.round=c.round and r.driver_code=c.driver_code;
            update marts.mart_race_story s set is_classified = r.is_classified
            from staging.stg_results r
            where s.season=r.season and s.round=r.round and s.driver_code=r.driver_code;
        """)
        source_sql = str(source.resolve()).replace("'", "''")
        conn.execute(f"attach '{source_sql}' as baseline (read_only)")
        relations = conn.sql("""
            select table_schema, table_name from information_schema.tables
            where table_catalog='baseline' and table_schema in ('staging','intermediate','marts')
            order by table_schema, table_name
        """).fetchall()
        for schema, table in relations:
            qualified = f'"{schema}"."{table}"'
            columns = (
                "* exclude (is_classified)"
                if (schema, table) in {("staging", "stg_results"), ("marts", "mart_race_story")}
                else "*"
            )
            for left, right in [
                (qualified, f"baseline.{qualified}"),
                (f"baseline.{qualified}", qualified),
            ]:
                difference = conn.execute(
                    f"select count(*) from (select {columns} from {left} "
                    f"except all select {columns} from {right})"
                ).fetchone()
                if difference != (0,):
                    raise ValueError(f"Unexpected non-classification changes in {qualified}")
        conn.execute("detach baseline")
    validate_dashboard_snapshot(output)
    if hashlib.sha256(source.read_bytes()).hexdigest() != source_hash:
        raise ValueError("Source changed during migration")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(
            {
                "method": "jolpica-position-text-v1",
                "source_sha256": source_hash,
                "candidate_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "changed_results": len(changed),
                "unchanged_non_classification_relations": len(relations),
                "corrections": json.loads(changed.to_json(orient="records")),
                "limitations": "Source classification, not an independent review of every result.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Corrected {len(changed)} results; all other columns/relations preserved")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    migrate(args.source, args.output, args.report)
