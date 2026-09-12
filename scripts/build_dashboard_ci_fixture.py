"""Build a compact, deterministic dashboard snapshot for PR validation.

The full dashboard database is intentionally not downloaded in CI. This fixture
keeps every published relation and one representative race while dropping raw
position ticks that no dashboard source reads directly.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

SCHEMAS = ("staging", "intermediate", "marts")
DEFAULT_SEASON = 2026
DEFAULT_ROUND = 12
SCHEMA_ONLY_TABLES = {("staging", "stg_positions"), ("staging", "stg_telemetry")}


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def build_fixture(source: Path, output: Path, *, season: int, round_number: int) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp.duckdb")
    temporary.unlink(missing_ok=True)

    connection = duckdb.connect(str(temporary))
    try:
        source_sql = str(source.resolve()).replace("'", "''")
        connection.execute(f"attach '{source_sql}' as source_snapshot (read_only)")
        for schema in SCHEMAS:
            connection.execute(f"create schema {_quote(schema)}")

        relations = connection.execute(
            "select table_schema, table_name from information_schema.tables "
            "where table_catalog = 'source_snapshot' and table_schema in (?, ?, ?) "
            "order by table_schema, table_name",
            list(SCHEMAS),
        ).fetchall()
        for schema, table in relations:
            columns = {
                str(row[0])
                for row in connection.execute(
                    "select column_name from information_schema.columns "
                    "where table_catalog = 'source_snapshot' and table_schema = ? and table_name = ?",
                    [schema, table],
                ).fetchall()
            }
            qualified = f"{_quote(schema)}.{_quote(table)}"
            source_qualified = f"source_snapshot.{qualified}"
            if (schema, table) in SCHEMA_ONLY_TABLES:
                predicate = "false"
                parameters: list[int] = []
            elif {"season", "round"}.issubset(columns):
                predicate = "season = ? and round = ?"
                parameters = [season, round_number]
            elif "season" in columns:
                predicate = "season = ?"
                parameters = [season]
            else:
                predicate = "true"
                parameters = []
            connection.execute(
                f"create table {qualified} as select * from {source_qualified} where {predicate}",
                parameters,
            )

        connection.execute("create schema dashboard")
        connection.execute(
            "create table dashboard.snapshot_metadata as "
            "select 'dashboard-ci-v1'::varchar as version, current_timestamp as generated_at, "
            "'ci-fixture'::varchar as source, max(race_date)::date as latest_event_date "
            "from staging.stg_races"
        )
        connection.execute("detach source_snapshot")
    finally:
        connection.close()

    temporary.replace(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("data/dashboard/latest.duckdb"))
    parser.add_argument("--output", type=Path, default=Path("tests/fixtures/dashboard-ci.duckdb"))
    parser.add_argument("--season", type=int, default=DEFAULT_SEASON)
    parser.add_argument("--round", dest="round_number", type=int, default=DEFAULT_ROUND)
    args = parser.parse_args()
    build_fixture(args.source, args.output, season=args.season, round_number=args.round_number)
    print(f"Built {args.output} ({args.output.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
