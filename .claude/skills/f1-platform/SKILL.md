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

**Status: all 5 milestones complete.** Branch `feat/api-data-expansion` (PR #8)
adds four new marts on top — pit strategy, weather-adjusted degradation,
straight-line speed, and resampled telemetry — verified live on 2024 data (see
"Further marts" below). The local Evidence dashboard runs at
http://localhost:3000 via `cd dashboard && npm run dev`.

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
Also `mart_stint_degradation` (per-driver-stint) and `mart_driver_season_pace`.

## Further marts (API expansion — PR #8, `feat/api-data-expansion`)

Surfaced from a full survey of what the two APIs expose. Each extends the stack
end-to-end (ingest → lake → warehouse → dbt → Dagster → Evidence page).

- **`mart_pit_strategy`** — undercut/overcut per pit stop: track-position swing
  (lap before vs two laps after) + stop duration. Pure **Ergast**
  (`raw.pitstops` + `raw.ergast_laps`, both per-round, ~2011+). Verified live on
  Bahrain 2024 (`dbt build +mart_pit_strategy` PASS=43).
- **`mart_weather_degradation`** — tyre fall-off (`regr_slope`) segmented by a
  race-day weather bucket (cool/hot/wet) from FastF1 `raw.weather`.
- **`mart_speed_trap`** — straight-line speed per driver per race (FastF1
  `SpeedST`, now kept on `raw.laps`). Range test scoped to `n_laps >= 3`.
- **`mart_lap_telemetry`** — car telemetry (speed/throttle/brake/DRS/gear/x/y)
  **resampled onto a uniform distance grid** (`F1_FASTF1_TELEMETRY_RESAMPLE_M`,
  default 25 m). ~242k rows per race at 25 m → low-millions per season. Dashboard
  `telemetry` page = speed traces + a gear-coloured track map (first ScatterPlot),
  fed by a fastest-lap-only Evidence source so the browser isn't handed the whole mart.

FastF1↔Ergast joins go through the existing `stg_driver_codes` season-grain bridge.

## File / module map

- `ingestion/` — EL package.
  - `config.py` (pydantic-settings, `F1_*` env, `.env`; incl. `fastf1_telemetry_resample_m`), `logging.py` (structlog).
  - `clients/jolpica.py` (rate-limited, retrying, paginating), `clients/fastf1_client.py` (lazy import; `load_session_laps` now keeps speed traps + `lap_start_sec`, plus `load_session_weather`, `load_session_telemetry`, and pure `resample_lap_telemetry`).
  - `resources.py` (season-scoped registry + flatteners races/results/qualifying; **per-round** flatteners `_flatten_pitstops`/`_flatten_ergast_laps`).
  - `loaders/lake.py` (Parquet), `loaders/warehouse.py` (idempotent-per-season load; `read_query`/`replace_table`).
  - `pipeline.py` (`ingest_resource`, `backfill`, `ingest_laps`, `ingest_pitstops`, `ingest_ergast_laps`, `ingest_weather`, `ingest_telemetry`, `season_rounds`), `cli.py` (`backfill`/`incremental`/`laps`/`pitstops`/`ergast-laps`/`weather`/`telemetry`).
- `analytics/` — `ratings.py` (pure solver + union-find), `pipeline.py` (`build_driver_ratings`), `cli.py`.
- `warehouse/dbt/` — `profiles.yml` (dev=duckdb, prod=postgres), `macros/` (`generate_schema_name`, `parse_laptime`),
  `models/staging|intermediate|marts/*.sql` + `_*.yml` tests, `snapshots/drivers_snapshot.sql`.
- `orchestration/` — `assets.py` (raw.* assets keyed to dbt sources — now also `raw_pitstops`/`raw_ergast_laps`/`raw_weather`/`raw_telemetry`, all `deps=[["raw","races"]]`; FastF1 assets ingest the current season *so far* via `season_rounds`; `@dbt_assets`, `driver_ratings`),
  `definitions.py` (job + weekly schedule + `DbtCliResource`; the weekly job **excludes** `raw.telemetry` — too heavy to re-pull weekly, materialise on demand).
- `dashboard/` — Evidence project: `sources/f1/*.sql` (over the marts), pages `index.md`, `race-pace.md`, `pit-strategy.md`, `weather-and-speed.md`, `telemetry.md`,
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
python -m ingestion.cli laps --season 2024                  # FastF1 laps (.[telemetry]); no --to-round = season so far
python -m ingestion.cli pitstops --season 2024              # Ergast pit stops (per-round)
python -m ingestion.cli ergast-laps --season 2024           # Ergast per-lap positions (per-round)
python -m ingestion.cli weather --season 2024               # FastF1 weather
python -m ingestion.cli telemetry --season 2024             # FastF1 telemetry (heavy: ~5.5 min/race)
dbt build --project-dir warehouse/dbt --profiles-dir warehouse/dbt --target dev   # or --target prod
python -m analytics.cli ratings --top 20                    # solve + print leaderboard
dagster dev -m orchestration.definitions                    # Dagster UI (run from repo root)
dagster definitions validate -m orchestration.definitions   # CI check
cd dashboard && npm run dev                                 # Evidence at localhost:3000
```
Makefile wraps these (`make lint typecheck test dbt-build dagster …`). For Postgres, load the existing lake instead of re-hitting the API: read each `data/raw/*/season=*/data.parquet` and call `load_dataframe(df, resource, season)` with `F1_WAREHOUSE=postgres`.

## Verification (known-good)

- Original stack: `dbt build` green on both `--target dev` and `--target prod`; solver spot-checks (Hamilton/Bottas 2019 gaps antisymmetric; Verstappen beat Perez 95% of 2023 quali).
- Post-expansion: `dbt parse`/`compile` = **20 models, 8 sources**; ruff + mypy(strict, ~25 files) clean; **18** pytest tests; `dagster definitions validate` passes.
- Expansion verified **live on 2024**: Ergast pit-strategy `dbt build +mart_pit_strategy` PASS=43; FastF1 laps(+speed traps)/weather/telemetry ingested and the three FastF1 marts built PASS=14. Spot-checks sane (Bahrain "cool" 23.7 °C night race; Sainz/Hülkenberg top the speed trap at 332 km/h).
- Ingestion idempotent per season (re-run keeps row counts; `tests/test_warehouse.py`).

## Gotchas / hard-won lessons (don't rediscover these)

- **mypy pinned `<2`**: mypy 2.x needs `pathspec>=1.0`, which conflicts with dbt's `pathspec<0.13`. Keep `mypy>=1.13,<2`.
- **Cross-dialect SQL**: use `double precision` (not `double`); `ln`, `regr_slope`, `strpos`, `split_part`, `stddev_samp` work on both; avoid `median` (use `avg`). Test both targets.
- **Solver**: plain Jacobi oscillates on bipartite teammate pairs — must use damping. Ratings only comparable within the largest connected component.
- **Dagster asset modules**: no `from __future__ import annotations` (breaks context/resource type introspection). `DbtCliResource` needs an explicit dbt executable path when the venv isn't on PATH (see `definitions.py:_dbt_executable`).
- **Evidence**: DuckDB `connection.yaml` `filename` is relative to the source folder → `../../../data/warehouse/f1.duckdb`. Project-site base path set in `evidence.config.yaml`.
- **GitHub token**: fine-grained PATs need explicit repo access + Contents(RW)+Pull requests(RW) for PRs, Administration(RW) for default-branch, Pages(RW) for Pages. `gh pr create` (GraphQL) failed on defaultBranchRef; create PRs via REST: `gh api -X POST repos/OWNER/REPO/pulls -f head= -f base= -f body=`.
- **Stacked PRs**: merging PR #1 to main first caused GitHub to retarget #2–#4 onto the intermediate branch, so they merged there, not main — needed a final `feat/dbt-core → main` PR. Prefer merging a stack bottom-up in one sitting.
- **FastF1 uses driver 3-letter codes** (VER), not Ergast `driver_id`; the laps/telemetry marts are keyed separately from the Jolpica marts, bridged by `stg_driver_codes` on `(season, driver_code)`.
- **Per-round endpoints** (Ergast pit stops / lap positions; FastF1 weather / telemetry) don't fit the season-scoped `Resource` registry. Use a dedicated `ingest_*` that concats **all rounds into one season frame and loads once** — the loader's delete key is `season` only, so loading round-by-round wipes earlier rounds.
- **Adding columns to an existing raw table** (e.g. speed traps on `raw.laps`): DuckDB `CREATE TABLE IF NOT EXISTS` won't add them and the positional INSERT then mismatches — **drop the table once and re-ingest**.
- **"Season so far"** (`season_rounds`) reads `raw.races` for dates ≤ today, so `races` must be backfilled first; it only returns rounds the real FastF1 feed actually has — test against a season with data (e.g. 2024), not a future season.
- **Telemetry is heavy** (~242k rows/race at 25 m ≈ low-millions/season; ~5.5 min/race). It's excluded from the weekly Dagster job (materialise on demand); the dashboard reads a fastest-lap-only source, not the full mart.

## Remaining / future work

- Enable GitHub Pages (Settings → Pages → GitHub Actions) + run the *Deploy Dashboard* workflow for the public URL.
- Merge PR #8, then **backfill the new marts for real**: pit stops / ergast-laps over ~2011→current, and FastF1 weather/telemetry across a full season (the live check only ingested 2024 R1 for weather/telemetry).
- Possible: a proper constructors/drivers dimension from the dedicated endpoints; driver-standings / championship-evolution mart; finer per-lap weather join (now that `lap_start_sec` is retained on `raw.laps`).
