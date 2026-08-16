"""Software-defined assets for the F1 pipeline.

Ingestion assets are keyed ``["raw", <table>]`` so they line up with the dbt
sources of the same name — dagster-dbt then wires the dbt models downstream
automatically. The Python rating solver depends on the dbt intermediate model.
"""

from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from analytics.pipeline import build_driver_ratings
from dagster import AssetExecutionContext, AssetKey, MaterializeResult, asset
from dagster_dbt import (
    DagsterDbtTranslator,
    DbtCliResource,
    DbtProject,
    dbt_assets,
)
from ingestion.pipeline import (
    ingest_ergast_laps,
    ingest_laps,
    ingest_pitstops,
    ingest_resource,
    ingest_telemetry,
    ingest_weather,
    season_rounds,
)

# Season the scheduled pipeline refreshes (mirrors the `incremental` CLI).
CURRENT_SEASON = 2026

_REPO_ROOT = Path(__file__).resolve().parent.parent
DBT_PROJECT_DIR = _REPO_ROOT / "warehouse" / "dbt"

dbt_project = DbtProject(project_dir=DBT_PROJECT_DIR)
dbt_project.prepare_if_dev()


# --- Ingestion assets (keyed to dbt sources) --------------------------------
@asset(key=["raw", "races"], group_name="ingest", compute_kind="jolpica")
def raw_races() -> MaterializeResult:
    rows = ingest_resource("races", CURRENT_SEASON)
    return MaterializeResult(metadata={"rows": rows, "season": CURRENT_SEASON})


@asset(key=["raw", "results"], group_name="ingest", compute_kind="jolpica")
def raw_results() -> MaterializeResult:
    rows = ingest_resource("results", CURRENT_SEASON)
    return MaterializeResult(metadata={"rows": rows, "season": CURRENT_SEASON})


@asset(key=["raw", "qualifying"], group_name="ingest", compute_kind="jolpica")
def raw_qualifying() -> MaterializeResult:
    rows = ingest_resource("qualifying", CURRENT_SEASON)
    return MaterializeResult(metadata={"rows": rows, "season": CURRENT_SEASON})


@asset(
    key=["raw", "laps"],
    deps=[AssetKey(["raw", "races"])],
    group_name="ingest",
    compute_kind="fastf1",
)
def raw_laps() -> MaterializeResult:
    rounds = season_rounds(CURRENT_SEASON, completed_only=True)
    rows = ingest_laps(CURRENT_SEASON, rounds, "R")
    return MaterializeResult(metadata={"rows": rows, "season": CURRENT_SEASON})


@asset(
    key=["raw", "pitstops"],
    deps=[AssetKey(["raw", "races"])],
    group_name="ingest",
    compute_kind="jolpica",
)
def raw_pitstops() -> MaterializeResult:
    rounds = season_rounds(CURRENT_SEASON, completed_only=True)
    rows = ingest_pitstops(CURRENT_SEASON, rounds)
    return MaterializeResult(metadata={"rows": rows, "season": CURRENT_SEASON})


@asset(
    key=["raw", "ergast_laps"],
    deps=[AssetKey(["raw", "races"])],
    group_name="ingest",
    compute_kind="jolpica",
)
def raw_ergast_laps() -> MaterializeResult:
    rounds = season_rounds(CURRENT_SEASON, completed_only=True)
    rows = ingest_ergast_laps(CURRENT_SEASON, rounds)
    return MaterializeResult(metadata={"rows": rows, "season": CURRENT_SEASON})


@asset(
    key=["raw", "weather"],
    deps=[AssetKey(["raw", "races"])],
    group_name="ingest",
    compute_kind="fastf1",
)
def raw_weather() -> MaterializeResult:
    rounds = season_rounds(CURRENT_SEASON, completed_only=True)
    rows = ingest_weather(CURRENT_SEASON, rounds, "R")
    return MaterializeResult(metadata={"rows": rows, "season": CURRENT_SEASON})


@asset(
    key=["raw", "telemetry"],
    deps=[AssetKey(["raw", "races"])],
    group_name="ingest",
    compute_kind="fastf1",
)
def raw_telemetry() -> MaterializeResult:
    # Heavy: resampled telemetry for every race lap of the season so far. Kept out
    # of the weekly refresh job (see definitions.py) — materialise on demand.
    rounds = season_rounds(CURRENT_SEASON, completed_only=True)
    rows = ingest_telemetry(CURRENT_SEASON, rounds, "R")
    return MaterializeResult(metadata={"rows": rows, "season": CURRENT_SEASON})


# --- dbt models -------------------------------------------------------------
class F1DbtTranslator(DagsterDbtTranslator):
    """Map dbt sources to the ingestion assets' ``["raw", <table>]`` keys."""

    def get_asset_key(self, dbt_resource_props: Mapping[str, Any]) -> AssetKey:
        if dbt_resource_props["resource_type"] == "source":
            return AssetKey(["raw", dbt_resource_props["name"]])
        return super().get_asset_key(dbt_resource_props)


@dbt_assets(manifest=dbt_project.manifest_path, dagster_dbt_translator=F1DbtTranslator())
def dbt_models(context: AssetExecutionContext, dbt: DbtCliResource) -> Iterator[Any]:
    yield from dbt.cli(["build"], context=context).stream()


# --- Analytics: the global rating solver ------------------------------------
@asset(
    deps=[AssetKey(["int_teammate_quali_gaps"]), AssetKey(["stg_drivers"])],
    group_name="analytics",
    compute_kind="python",
)
def driver_ratings() -> MaterializeResult:
    df = build_driver_ratings()
    top = df.iloc[0]
    return MaterializeResult(
        metadata={"drivers": len(df), "fastest": f"{top['driver_name']} ({top['rating']:.3f})"}
    )
