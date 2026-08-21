"""Integration tests for the Python-written analytics marts.

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
from analytics.pipeline import build_driver_pace_profile, build_driver_ratings
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


# The exact column contract the Saturday-vs-Sunday page and its source depend on.
PROFILE_EXPECTED_COLUMNS = [
    "delta_rank",
    "driver_id",
    "driver_name",
    "nationality",
    "quali_rating",
    "race_rating",
    "delta",
    "quali_rank",
    "race_rank",
    "n_quali_comparisons",
    "n_race_comparisons",
    "n_seasons",
    "first_season",
    "last_season",
]


def _seed_pace_profile_warehouse(db_path: Path) -> None:
    """Seed the three tables ``build_driver_pace_profile`` reads from.

    Qualifying spans 2018-2021 but race pace only 2020-2021, so the season match
    inside the pure module has something to actually bite on: the 2018-2019
    qualifying rows must not influence the fitted quali rating.
    """
    quali = pd.concat(
        [
            # Early seasons: A dominates. These must be excluded by the match.
            _seasoned_gaps([("A", "B", -6.0), ("B", "C", -1.0)], seasons=[2018, 2019]),
            # Matched seasons: A only just ahead of B.
            _seasoned_gaps([("A", "B", -1.0), ("B", "C", -1.0)], seasons=[2020, 2021]),
        ],
        ignore_index=True,
    )
    # In the race B is ahead of A, so B is the racer and A the quali specialist.
    race = _seasoned_gaps([("A", "B", 1.0), ("B", "C", -1.0)], seasons=[2020, 2021])
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
        con.register("quali", quali)
        con.register("race", race)
        con.register("drivers", drivers)
        con.execute("create table intermediate.int_teammate_quali_gaps as select * from quali")
        con.execute("create table intermediate.int_teammate_race_gaps as select * from race")
        con.execute("create table staging.stg_drivers as select * from drivers")
    finally:
        con.unregister("quali")
        con.unregister("race")
        con.unregister("drivers")
        con.close()  # release the single writer before read_query opens read-only


def test_build_driver_pace_profile_materialises_mart(tmp_path: Path) -> None:
    db_path = tmp_path / "f1.duckdb"
    _seed_pace_profile_warehouse(db_path)
    settings = Settings(warehouse="duckdb", duckdb_path=db_path)

    result = build_driver_pace_profile(settings=settings)

    assert list(result.columns) == PROFILE_EXPECTED_COLUMNS
    assert len(result) == 3
    assert sorted(result["delta_rank"]) == [1, 2, 3]

    # B gains most between Saturday and Sunday; A loses most.
    ordered = result.sort_values("delta_rank")["driver_id"].tolist()
    assert ordered[0] == "B"
    assert ordered[-1] == "A"

    d = result.set_index("driver_id")
    assert d.loc["B", "delta"] > 0
    assert d.loc["A", "delta"] < 0

    # Season span comes from the race gaps, which only cover 2020-2021.
    assert set(d["first_season"]) == {2020}
    assert set(d["last_season"]) == {2021}
    assert set(d["n_seasons"]) == {2}

    # The join to stg_drivers populated the display fields.
    assert d["driver_name"].notna().all()

    # And it really landed in the warehouse, readable by the dashboard source.
    persisted = read_query("select * from marts.driver_pace_profile", settings)
    assert len(persisted) == 3
    assert list(persisted.columns) == PROFILE_EXPECTED_COLUMNS


def test_pace_profile_season_bounds_filter_the_race_gaps(tmp_path: Path) -> None:
    db_path = tmp_path / "f1.duckdb"
    _seed_pace_profile_warehouse(db_path)
    settings = Settings(warehouse="duckdb", duckdb_path=db_path)

    result = build_driver_pace_profile(from_season=2021, settings=settings)

    assert set(result["first_season"]) == {2021}
    assert set(result["n_seasons"]) == {1}
