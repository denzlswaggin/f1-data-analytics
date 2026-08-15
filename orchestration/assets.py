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
from ingestion.pipeline import ingest_laps, ingest_resource

# Season the scheduled pipeline refreshes (mirrors the `incremental` CLI).
CURRENT_SEASON = 2026
# Sample race laps for the telemetry mart (FastF1).
LAPS_SEASON = 2024
LAPS_ROUNDS = [1, 2, 3, 4, 5]

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


@asset(key=["raw", "laps"], group_name="ingest", compute_kind="fastf1")
def raw_laps() -> MaterializeResult:
    rows = ingest_laps(LAPS_SEASON, LAPS_ROUNDS, "R")
    return MaterializeResult(metadata={"rows": rows, "season": LAPS_SEASON})


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
