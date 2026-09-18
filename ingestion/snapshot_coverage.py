"""Serving-source availability and explicit publication regression checks."""

from pathlib import Path

import duckdb

SOURCE_TABLES = {
    "pitstops": "marts.mart_pit_strategy",
    "weather": "staging.stg_weather",
    "team_radio": "staging.stg_team_radio",
}


def materialize_source_coverage(c: duckdb.DuckDBPyConnection) -> None:
    c.execute("""create table if not exists marts.source_coverage (
        resource varchar, season integer, round integer, status varchar,
        row_count bigint, provenance varchar, source_sha256 varchar, reason varchar)""")
    for resource, table in SOURCE_TABLES.items():
        c.execute(f"""create or replace temp table source_counts as
            select season, round, count(*) as n from {table} group by season, round""")
        c.execute(
            """insert into marts.source_coverage
            (resource, season, round, status, row_count, provenance, source_sha256, reason)
            select ?, r.season, r.round,
                case when coalesce(s.n,0)>0 then 'available' else 'not_attempted' end,
                coalesce(s.n,0), 'warehouse', null,
                case when coalesce(s.n,0)>0 then '' else 'No observations or attempt receipt' end
            from (select distinct season,round from staging.stg_results where season>=2024) r
            left join source_counts s using(season,round)
            where not exists(select 1 from marts.source_coverage old
                where old.resource=? and old.season=r.season and old.round=r.round)""",
            [resource, resource],
        )
        c.execute(
            """update marts.source_coverage set row_count=coalesce((
            select n from source_counts s where s.season=source_coverage.season
                and s.round=source_coverage.round),0) where resource=?""",
            [resource],
        )
        c.execute(
            """update marts.source_coverage set status='available',reason=''
            where resource=? and row_count>0""",
            [resource],
        )
        c.execute(
            """update marts.source_coverage set status='unavailable',
            reason='Previously available source has no exported observations'
            where resource=? and row_count=0 and status='available'""",
            [resource],
        )


def validate_partition_preservation(
    previous: Path, candidate: Path, exceptions: list[dict[str, object]] | None = None
) -> None:
    """Reject disappearing partitions; accepted exceptions name a table/race/reason."""
    if not previous.is_file():
        return
    allowed = {}
    for entry in exceptions or []:
        if not str(entry.get("reason", "")).strip():
            raise ValueError("Coverage exception requires a nonempty reason")
        allowed[(entry["table"], int(str(entry["season"])), int(str(entry["round"])))] = entry[
            "reason"
        ]
    with (
        duckdb.connect(str(previous), read_only=True) as old,
        duckdb.connect(str(candidate), read_only=True) as new,
    ):
        tables = old.execute("""select table_schema||'.'||table_name from information_schema.columns
            where table_schema in ('staging','marts','intermediate')
            and column_name in ('season','round') group by table_schema,table_name
            having count(distinct column_name)=2""").fetchall()
        lost: list[tuple[object, ...]] = []
        for (table,) in tables:
            columns = {row[0] for row in old.execute(f"describe {table}").fetchall()}
            keys = "season,round,session" if "session" in columns else "season,round"
            before = set(old.execute(f"select distinct {keys} from {table}").fetchall())
            try:
                after = set(new.execute(f"select distinct {keys} from {table}").fetchall())
            except (duckdb.CatalogException, duckdb.BinderException):
                after = set()
            lost.extend(
                (table, *key) for key in before - after if (table, key[0], key[1]) not in allowed
            )
        if lost:
            raise ValueError(f"Snapshot would lose published partitions: {sorted(lost)}")


def validate_source_coverage(c: duckdb.DuckDBPyConnection) -> None:
    """Require an auditable attempt for each optional source in completed races."""
    for resource, table in SOURCE_TABLES.items():
        invalid = c.execute(
            f"""
            with actual as (
                select season, round, count(*) as n from {table} group by season, round
            )
            select races.season, races.round
            from (select distinct season, round from staging.stg_results where season >= 2024) races
            left join marts.source_coverage as ledger
                on ledger.resource = ? and ledger.season = races.season and ledger.round = races.round
            left join actual on actual.season = races.season and actual.round = races.round
            where ledger.status is null
                or ledger.status not in ('available', 'no_observations', 'unavailable')
                or ledger.row_count is distinct from coalesce(actual.n, 0)
                or (ledger.status = 'available' and coalesce(actual.n, 0) = 0)
                or (ledger.status <> 'available' and coalesce(actual.n, 0) > 0)
                or (ledger.status <> 'available' and coalesce(trim(ledger.reason), '') = '')
        """,
            [resource],
        ).fetchall()
        duplicates = c.execute(
            """select season, round from marts.source_coverage
            where resource = ? group by season, round having count(*) <> 1""",
            [resource],
        ).fetchall()
        if invalid or duplicates:
            raise ValueError(
                f"Source coverage invalid for {resource}: {invalid}; duplicates={duplicates}"
            )
