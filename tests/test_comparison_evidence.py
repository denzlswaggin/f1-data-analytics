"""Shared-season comparisons preserve estimates without inventing probabilities."""

from __future__ import annotations

import re
from pathlib import Path

import duckdb


def query(page: str, name: str, replacements: dict[str, str]) -> str:
    text = Path(f"dashboard/pages/{page}.md").read_text(encoding="utf-8")
    match = re.search(rf"```sql {name}\n(.*?)\n```", text, re.S)
    assert match is not None
    sql = match[1]
    for key, value in replacements.items():
        sql = sql.replace("${inputs." + key + ".value}", value)
    return sql


def connection() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    conn.execute("create schema f1")
    conn.execute("""create table f1.driver_ratings_v2 as
        select 2024 as season, 'a' as driver_id, 'Driver A' as driver_name,
            0.8 as rating, 0.5 as rating_lo, 1.0 as rating_hi,
            0.1 as form_delta, 12 as n_comparisons
        union all select 2024,'b','Driver B',0.3,0.1,0.6,0.2,8
        union all select 2023,'a','Driver A',0.6,0.3,0.9,0.1,10
        union all select 2022,'b','Driver B',0.2,null,null,0.1,3""")
    return conn


def test_only_shared_seasons_enter_chart_and_comparison() -> None:
    inputs = {"driver_a": "a", "driver_b": "b"}
    with connection() as conn:
        chart = conn.sql(query("driver-comparison", "comparison", inputs)).df()
        comparison = conn.sql(query("driver-comparison", "shared_comparison", inputs)).df()
    assert chart.season.tolist() == [2024, 2024]
    assert comparison.season.tolist() == [2024]
    row = comparison.iloc[0]
    assert row.rating_delta == 0.5
    assert (row.a_lo, row.a_hi, row.b_lo, row.b_hi) == (0.5, 1.0, 0.1, 0.6)
    assert (row.a_comparisons, row.b_comparisons) == (12, 8)
    assert not any("probability" in column for column in comparison.columns)


def test_same_driver_is_zero_and_missing_shared_data_stays_empty() -> None:
    with connection() as conn:
        same = conn.sql(
            query("driver-comparison", "shared_comparison", {"driver_a": "a", "driver_b": "a"})
        ).df()
        missing = conn.sql(
            query(
                "driver-comparison", "shared_comparison", {"driver_a": "a", "driver_b": "missing"}
            )
        ).df()
    assert same.rating_delta.eq(0).all()
    assert missing.empty


def test_cockpit_distinguishes_processed_zero_from_unavailable_analysis() -> None:
    with duckdb.connect() as conn:
        conn.execute("create schema f1")
        conn.execute("""create table f1.racecraft_coverage as
            select 2025 as season, 1 as round, 'No replay available' as coverage_status,
                null::integer as detected_passes
            union all select 2025, 2, 'Processed: no observed battles', 0
            union all select 2025, 3, 'Unverified processing: rebuild required', 4""")
        for rnd, expected in ((1, []), (2, [0]), (3, [])):
            result = conn.sql(
                query("race-cockpit", "pass_summary", {"season": "2025", "race": str(rnd)})
            ).df()
            assert result.passes.tolist() == expected


def test_cockpit_control_zero_requires_observed_messages() -> None:
    with duckdb.connect() as conn:
        conn.execute("create schema f1")
        conn.execute("""create table f1.race_control_races as
            select 2025 as season, 1 as round, 0 as message_count, 0 as event_count
            union all select 2025, 2, 12, 0
            union all select 2025, 3, 12, 1""")
        conn.execute("""create table f1.race_control_events as
            select 2025 as season, 3 as round, 2 as intervention_stop_count,
                   3 as position_gainer_count""")
        for rnd, expected in ((1, []), (2, [(0, 0, 0)]), (3, [(1, 2, 3)])):
            result = conn.execute(
                query("race-cockpit", "control_summary", {"season": "2025", "race": str(rnd)})
            ).fetchall()
            assert result == expected
