"""Integration test for the headline ratings mart.

``build_driver_ratings`` reads two warehouse tables, runs the solver, enriches,
and writes ``marts.driver_ratings`` — the leaderboard the whole project is built
around, and previously the least-tested table in the repo. This seeds a throwaway
DuckDB warehouse (``duckdb`` is a core dependency, so it runs in CI without the
dbt/telemetry extras), runs the real function, and asserts the persisted mart.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
from analytics.pipeline import build_driver_ratings
from ingestion.config import Settings
from ingestion.loaders.warehouse import read_query

# The exact column contract the Evidence dashboard and blog table depend on.
EXPECTED_COLUMNS = [
    "rank",
    "driver_id",
    "driver_name",
    "nationality",
    "rating",
    "pace_deficit",
    "n_comparisons",
    "n_seasons",
    "first_season",
    "last_season",
]


def _seasoned_gaps(pairs: list[tuple[str, str, float]], seasons: list[int]) -> pd.DataFrame:
    """Directed teammate-gap rows (plus antisymmetric mirror) repeated per season."""
    rows: list[dict[str, object]] = []
    for season in seasons:
        for driver, teammate, gap in pairs:
            rows.append(
                {"driver_id": driver, "teammate_id": teammate, "pace_gap": gap, "season": season}
            )
            rows.append(
                {"driver_id": teammate, "teammate_id": driver, "pace_gap": -gap, "season": season}
            )
    return pd.DataFrame(rows)


def _seed_warehouse(db_path: Path) -> None:
    """Create the two upstream tables ``build_driver_ratings`` reads from."""
    # A faster than B by 1, B faster than C by 1, across two seasons.
    gaps = _seasoned_gaps([("A", "B", -1.0), ("B", "C", -1.0)], seasons=[2020, 2021])
    drivers = pd.DataFrame(
        [
            {"driver_id": "A", "driver_name": "Driver A", "nationality": "British"},
            {"driver_id": "B", "driver_name": "Driver B", "nationality": "German"},
            {"driver_id": "C", "driver_name": "Driver C", "nationality": "Spanish"},
        ]
    )
    con = duckdb.connect(str(db_path))
    try:
        con.execute("create schema intermediate")
        con.execute("create schema staging")
        con.register("gaps", gaps)
        con.register("drivers", drivers)
        con.execute("create table intermediate.int_teammate_quali_gaps as select * from gaps")
        con.execute("create table staging.stg_drivers as select * from drivers")
    finally:
        con.unregister("gaps")
        con.unregister("drivers")
        con.close()  # release the single writer before read_query opens read-only


def test_build_driver_ratings_materialises_mart(tmp_path: Path) -> None:
    db_path = tmp_path / "f1.duckdb"
    _seed_warehouse(db_path)
    settings = Settings(warehouse="duckdb", duckdb_path=db_path)

    result = build_driver_ratings(settings)

    # Column contract and one row per driver in the (single) connected component.
    assert list(result.columns) == EXPECTED_COLUMNS
    assert len(result) == 3

    # Ranks are contiguous 1..N and A (fastest) is on top.
    assert sorted(result["rank"]) == [1, 2, 3]
    assert list(result.sort_values("rank")["driver_id"]) == ["A", "B", "C"]

    # The join to stg_drivers populated the display fields.
    assert result["driver_name"].notna().all()
    a_row = result.set_index("driver_id").loc["A"]
    assert a_row["driver_name"] == "Driver A"
    assert a_row["nationality"] == "British"

    # The per-driver span aggregation reflects the two seeded seasons.
    assert a_row["n_seasons"] == 2
    assert a_row["first_season"] == 2020
    assert a_row["last_season"] == 2021

    # The mart was actually persisted, not just returned.
    persisted = read_query("select * from marts.driver_ratings", settings)
    assert len(persisted) == 3
    assert set(persisted["driver_id"]) == {"A", "B", "C"}
