---
name: f1-platform
description: >
  Full context for the f1-data-analytics data-engineering platform in this repo:
  architecture, the two insights and their methodology, a file/module map, run
  commands for every layer, environment setup, verification steps, and hard-won
  gotchas. Load this at the start of any session working on f1-data-analytics
  (ingestion, dbt models, the driver-rating solver, Dagster, or the Evidence
  dashboard) so you don't have to re-derive how the project fits together.
---

# F1 Analytics Engineering Platform — project context

A CV-centerpiece **data-engineering** project: a modern data stack that turns raw
F1 data into two reproducible, debatable insights. Owner: denzlswaggin
(patrik.kriz@studyfi.com). Repo: github.com/denzlswaggin/f1-data-analytics.

**Status: all 5 milestones complete; `main` is green and the sole branch.** The
local Evidence dashboard runs at http://localhost:3000 via `cd dashboard && npm run dev`.

## Architecture

```
Jolpica-F1 API + FastF1 ─► Ingestion (Python EL) ─► Parquet lake ─► DuckDB (dev) / Postgres (prod)
                                                                        │
                                                          dbt (staging → intermediate → marts) + snapshot
                                                                        │
                     ┌──────────────────────────────────┬─────────────┘
              Python rating solver                 Dagster assets (schedule)
              (marts.driver_ratings)                     │
                     └────────────► Evidence.dev dashboard ─► GitHub Pages
```

## Tech stack

| Layer | Tool |
|---|---|
| Sources | Jolpica-F1 (`https://api.jolpi.ca/ergast/f1`, post-Ergast successor) · FastF1 3.x (2018+ telemetry) |
| Ingestion | Python, `requests`, `tenacity`, `pydantic-settings`, `structlog`, Typer |
| Lake | Parquet (`pyarrow`), partitioned by season |
| Warehouse | DuckDB (dev) + Postgres 16 via docker-compose (prod) |
| Transform | dbt (`dbt-duckdb`, `dbt-postgres`), `dbt_utils`, `dbt_expectations` |
| Analytics | numpy least-squares solver (Massey-style) |
| Orchestration | Dagster + dagster-dbt |
| Serving | Evidence.dev (BI-as-code) → GitHub Pages |
| Quality/CI | ruff, mypy(strict), pytest, sqlfluff, GitHub Actions |

## The two insights

**1. Teammate-normalised "true pace" driver ratings** (the headline).
Teammates share a car, so their qualifying gap isolates driver skill. Pipeline:
`stg_qualifying` (Q1/Q2/Q3 → seconds) → `int_teammate_quali_gaps` (compare the two
teammates in the last knockout session both set a time in; gap =
`100*(ln(t_driver)-ln(t_teammate))`, antisymmetric + additive) → `analytics/ratings.py`
solves `min Σ(d_i−d_j−gap)²` on the teammate graph via **damped Jacobi** iteration
with **empirical-Bayes shrinkage**, over the **largest connected component** →
`marts.driver_ratings`. 2006–2025 result: Verstappen #1, then Russell, Leclerc,
Ricciardo, Vettel; Hamilton mid-pack (metric = margin over teammate).

**2. Tyre degradation** (`marts.mart_tyre_degradation`): `regr_slope(lap_time, tyre_life)`
per race/compound over green-flag laps. Lands soft +0.24 / medium +0.02 / hard ~0 s/lap.

## File / module map

- `ingestion/` — EL package.
  - `config.py` (pydantic-settings, `F1_*` env, `.env`), `logging.py` (structlog).
  - `clients/jolpica.py` (rate-limited, retrying, paginating), `clients/fastf1_client.py` (lazy import).
  - `resources.py` (declarative resource registry + flatteners: races/results/qualifying).
  - `loaders/lake.py` (Parquet), `loaders/warehouse.py` (idempotent-per-season load; `read_query`/`replace_table`).
  - `pipeline.py` (`ingest_resource`, `backfill`, `ingest_laps`), `cli.py` (`backfill`/`incremental`/`laps`).
- `analytics/` — `ratings.py` (pure solver + union-find), `pipeline.py` (`build_driver_ratings`), `cli.py`.
- `warehouse/dbt/` — `profiles.yml` (dev=duckdb, prod=postgres), `macros/` (`generate_schema_name`, `parse_laptime`),
  `models/staging|intermediate|marts/*.sql` + `_*.yml` tests, `snapshots/drivers_snapshot.sql`.
- `orchestration/` — `assets.py` (raw.* assets keyed to dbt sources, `@dbt_assets`, `driver_ratings` asset),
  `definitions.py` (job + weekly schedule + `DbtCliResource`).
- `dashboard/` — Evidence project: `sources/f1/*.sql` (over the marts), `pages/index.md` + `pages/race-pace.md`,
  `evidence.config.yaml` (`deployment.basePath: /f1-data-analytics`).
- `.github/workflows/` — `ci.yml` (quality + dbt + orchestration jobs), `scheduled-ingest.yml`, `deploy-dashboard.yml`.
- `docs/` — `blog-teammate-normalised-pace.md`, `linkedin-post.md`.

## Environment & setup

- **Python 3.12, 64-bit** (`py -3.12`). The machine's default `python` is 32-bit — DO NOT use it (pyarrow/duckdb ship 64-bit-only wheels). Venv at `.venv`.
- Install: `pip install -e ".[dev]"`; extras: `.[dbt]`, `.[telemetry]` (fastf1), `.[orchestration]` (dagster).
- Postgres: `docker compose up -d postgres` (Docker Desktop must be running; on Windows launch it, poll `docker info`). Creds f1/f1/f1.
- Config via `F1_*` env / `.env` (see `.env.example`). Key: `F1_WAREHOUSE=duckdb|postgres`, `F1_DUCKDB_PATH=data/warehouse/f1.duckdb`.

## Run commands

```bash
python -m ingestion.cli backfill --from 2006 --to 2025      # Jolpica → dev DuckDB
python -m ingestion.cli laps --season 2024 --from-round 1 --to-round 5   # FastF1 laps (.[telemetry])
dbt build --project-dir warehouse/dbt --profiles-dir warehouse/dbt --target dev   # or --target prod
python -m analytics.cli ratings --top 20                    # solve + print leaderboard
dagster dev -m orchestration.definitions                    # Dagster UI (run from repo root)
dagster definitions validate -m orchestration.definitions   # CI check
cd dashboard && npm run dev                                 # Evidence at localhost:3000
```
Makefile wraps these (`make lint typecheck test dbt-build dagster …`). For Postgres, load the existing lake instead of re-hitting the API: read each `data/raw/*/season=*/data.parquet` and call `load_dataframe(df, resource, season)` with `F1_WAREHOUSE=postgres`.

## Verification (known-good)

- `dbt build` **61/61** on both `--target dev` and `--target prod`.
- ruff + mypy(strict, ~23 files) clean; **11** pytest tests.
- Ingestion idempotent per season (re-run keeps row counts).
- `dagster definitions validate` passes; materialising `driver_ratings` via Dagster = RUN_SUCCESS.
- Spot-checks: Hamilton/Bottas 2019 gaps antisymmetric; Verstappen beat Perez 95% of 2023 quali.

## Gotchas / hard-won lessons (don't rediscover these)

- **mypy pinned `<2`**: mypy 2.x needs `pathspec>=1.0`, which conflicts with dbt's `pathspec<0.13`. Keep `mypy>=1.13,<2`.
- **Cross-dialect SQL**: use `double precision` (not `double`); `ln`, `regr_slope`, `strpos`, `split_part`, `stddev_samp` work on both; avoid `median` (use `avg`). Test both targets.
- **Solver**: plain Jacobi oscillates on bipartite teammate pairs — must use damping. Ratings only comparable within the largest connected component.
- **Dagster asset modules**: no `from __future__ import annotations` (breaks context/resource type introspection). `DbtCliResource` needs an explicit dbt executable path when the venv isn't on PATH (see `definitions.py:_dbt_executable`).
- **Evidence**: DuckDB `connection.yaml` `filename` is relative to the source folder → `../../../data/warehouse/f1.duckdb`. Project-site base path set in `evidence.config.yaml`.
- **GitHub token**: fine-grained PATs need explicit repo access + Contents(RW)+Pull requests(RW) for PRs, Administration(RW) for default-branch, Pages(RW) for Pages. `gh pr create` (GraphQL) failed on defaultBranchRef; create PRs via REST: `gh api -X POST repos/OWNER/REPO/pulls -f head= -f base= -f body=`.
- **Stacked PRs**: merging PR #1 to main first caused GitHub to retarget #2–#4 onto the intermediate branch, so they merged there, not main — needed a final `feat/dbt-core → main` PR. Prefer merging a stack bottom-up in one sitting.
- **FastF1 uses driver 3-letter codes** (VER), not Ergast `driver_id`; the laps/telemetry marts are keyed separately from the Jolpica marts.

## Remaining / future work

- Enable GitHub Pages (Settings → Pages → GitHub Actions) + run the *Deploy Dashboard* workflow for the public URL.
- Deferred: **undercut/overcut pit-strategy mart** (needs pit-stop timing + per-lap positions).
- Possible: more FastF1 seasons of laps; a proper constructors/drivers dimension from the dedicated endpoints; per-driver-stint (not pooled) degradation.
