# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

An end-to-end **data-engineering** platform for Formula 1: reliable ingestion → a versioned warehouse →
tested dbt transformations → orchestration → a SQL-native dashboard, powering a signature insight that
isolates **driver skill from car performance**. (The `f1-platform` skill covers the same ground in more
depth plus verification spot-checks; this file is meant to stand on its own.)

## Environment (read before running anything)

- **Python 3.12, 64-bit** (`py -3.12 -m venv .venv`). The machine's default `python` is 32-bit —
  do NOT use it; `pyarrow`/`duckdb` ship 64-bit-only wheels. Activate with `.venv\Scripts\activate` (PowerShell).
- Core install `pip install -e ".[dev]"`. Extras are deliberately separate: `.[dbt]` (strict transitive
  pins, resolved apart from the core), `.[telemetry]` (FastF1 — heavy, pulls matplotlib/scipy),
  `.[orchestration]` (Dagster). The FastF1 client imports lazily so the core install/CI stay lean.
- Config is `F1_*` env vars / `.env` (copy `.env.example`). Key knobs: `F1_WAREHOUSE=duckdb|postgres`,
  `F1_DUCKDB_PATH=data/warehouse/f1.duckdb`. Prod Postgres 16 = `docker compose up -d postgres` (creds f1/f1/f1;
  Docker Desktop must be running — on Windows launch it and poll `docker info`).

## Commands

`make help` lists all targets. Common ones:

```bash
make check            # lint + typecheck + test — run before pushing
make lint             # ruff check + ruff format --check
make format           # ruff format + ruff check --fix
make typecheck        # mypy (strict) over ingestion analytics orchestration tests
make test             # pytest -q
pytest tests/test_ratings.py::test_name   # single test
make dbt-build        # dbt build, dev target (DuckDB)
make dbt-docs         # dbt docs generate (dev)
make dagster-validate # assert Dagster definitions load — CI gate
make dagster          # launch Dagster UI (asset graph + schedules)
```

Full pipeline, in order:

```bash
python -m ingestion.cli backfill --from 2006 --to 2025   # Jolpica → Parquet lake → dev DuckDB (~17k rows)
python -m ingestion.cli laps --season 2024 --from-round 1 --to-round 5   # FastF1 laps (.[telemetry])
make dbt-build                                           # staging → intermediate → marts (61 models)
python -m analytics.cli ratings --top 20                 # solve + print driver leaderboard
python -m analytics.cli pace-profile --from-season 2022  # Saturday-vs-Sunday delta (needs FastF1 laps)
cd dashboard && npm run dev                              # Evidence dashboard at localhost:3000
```

dbt runs are wrapped by the Makefile; the raw form is
`dbt build --project-dir warehouse/dbt --profiles-dir warehouse/dbt --target dev` (`--target prod` for
Postgres). **Always build SQL changes on both targets.** For Postgres, load the existing lake rather than
re-hitting the API: read each `data/raw/*/season=*/data.parquet` and call `load_dataframe(df, resource,
season)` with `F1_WAREHOUSE=postgres`. Console scripts `f1-ingest` and `f1-analytics` alias the two CLIs.

## Architecture (the big picture)

Data flows **Jolpica-F1 API + FastF1 → `ingestion/` (Python EL) → Parquet lake (`data/raw/`, partitioned
by season) → DuckDB (dev) / Postgres (prod) → dbt (`warehouse/dbt/`) → { `analytics/` solver, Dagster,
Evidence dashboard → GitHub Pages }**.

- **`ingestion/`** — EL package. `resources.py` is a declarative resource registry + flatteners
  (races/results/qualifying); clients are `jolpica.py` (rate-limited, retrying, paginating) and
  `fastf1_client.py` (lazy import); `loaders/lake.py` writes Parquet, `loaders/warehouse.py` loads
  idempotently per season (`read_query`/`replace_table`/`load_dataframe`). `pipeline.py` has
  `ingest_resource`/`backfill`/`ingest_laps`; `cli.py` is the Typer entrypoint (`backfill`/`incremental`/`laps`).
  `config.py` = pydantic-settings, `logging.py` = structlog.
- **`warehouse/dbt/`** — `staging → intermediate → marts`. `profiles.yml` has dev=duckdb, prod=postgres.
  dbt marts are `mart_driver_season_pace`, `mart_lap_times`, `mart_tyre_degradation`.
  Model-level thresholds live in `vars:` in `dbt_project.yml` (the `race_gap_*` knobs). `macros/` holds
  `generate_schema_name` and `parse_laptime`. Tests via `dbt_utils` + `dbt_expectations`. A
  `drivers_snapshot` snapshot tracks driver SCD.
- **`analytics/`** — the headline `driver_ratings` insight is **NOT a dbt model**. `ratings.py` is a pure
  numpy Massey-style least-squares solver with union-find; `pace_profile.py` reuses that solver for the
  race-pace rating and joins the two into `driver_pace_profile`; `pipeline.py`
  (`build_driver_ratings` / `build_driver_pace_profile`) writes the tables; `cli.py` prints the leaderboards
  (`ratings`, `pace-profile`).
- **`orchestration/`** — Dagster. `assets.py` mirrors dbt sources as `raw.*` assets, wraps the dbt project
  via `@dbt_assets`, and adds the `driver_ratings` asset; `definitions.py` holds the job, a weekly
  race-weekend schedule, and the `DbtCliResource`.
- **`dashboard/`** — Evidence.dev (BI-as-code). `sources/f1/*.sql` query the marts; `pages/index.md`,
  `pages/race-pace.md` and `pages/saturday-vs-sunday.md` render. `evidence.config.yaml` sets `deployment.basePath: /f1-data-analytics`.
- **`.github/workflows/`** — `ci.yml` (quality + dbt + orchestration jobs), `scheduled-ingest.yml`,
  `deploy-dashboard.yml`.

## The three insights (methodology)

1. **Teammate-normalised "true pace" driver ratings** (headline). Teammates share a car, so the
   *qualifying gap between teammates* isolates driver skill. `stg_qualifying` (Q1/Q2/Q3 → seconds) →
   `int_teammate_quali_gaps` (compare the two teammates in the last knockout session both set a time in;
   gap = `100*(ln(t_driver) - ln(t_teammate))`, antisymmetric + additive) → `analytics/ratings.py` solves
   `min Σ(d_i − d_j − gap)²` on the teammate graph via **damped Jacobi** iteration with **empirical-Bayes
   shrinkage**, over the **largest connected component** → `driver_ratings`. 2006–2025: Verstappen #1, then
   Russell, Leclerc, Ricciardo, Vettel; Hamilton mid-pack (the metric measures *margin over teammate*).
2. **Saturday vs Sunday** (`marts.driver_pace_profile`): the same teammate-normalisation applied to *race*
   pace. `int_teammate_race_gaps` pairs teammates on the **same lap number** (identical fuel load) over
   green-flag laps on the **same compound** within a few laps of tyre age, drops the start lap / in-out laps /
   outliers, and averages to the quali model's grain — so `compute_ratings` consumes it unchanged.
   `analytics/pace_profile.py` then solves both and reports `delta = race_rating - quali_rating`
   (positive = racer, negative = qualifying specialist). Qualifying is **re-solved over only the seasons the
   race gaps cover** — the season set is derived from `race_gaps` inside the pure module, not from a matching
   SQL filter, so the two ratings can never describe different eras. Comparability thresholds are dbt vars
   (`race_gap_max_tyre_delta`, `race_gap_outlier_pct`, `race_gap_min_laps`).
3. **Tyre degradation** (`mart_tyre_degradation`): `regr_slope(lap_time, tyre_life)` per race/compound over
   green-flag laps. Lands soft +0.24 / medium +0.02 / hard ~0 s/lap.

## Gotchas that will bite you

- **mypy is pinned `<2`** — mypy 2.x needs `pathspec>=1.0`, which conflicts with dbt's `pathspec<0.13`.
  Keep `mypy>=1.13,<2`. **The pin is no longer enough on its own**: current mypy 1.x (1.20) also imports
  `pathspec.patterns.gitignore`, which dbt's `pathspec 0.12` doesn't have — so mypy *crashes* in any venv where
  `.[dev]` and `.[dbt]` are co-installed. CI dodges this because the Quality job installs only `.[dev]` and
  runs `mypy ingestion analytics tests` (note: **not** `orchestration`, unlike `make typecheck`). Locally, keep
  a separate dev-only venv for typechecking rather than one venv with every extra.
- **`dagster definitions validate` fails after a seeded dbt build** — `dbt build --vars '{load_ci_seeds: true}'`
  writes a manifest where the CI seeds are enabled, and each seed then collides with the `raw.*` source of the
  same name on its Dagster asset key. It's not a code fault: re-run a plain `dbt parse` (no vars) to regenerate
  a clean manifest before validating, which is what CI's orchestration job does.
- **Cross-dialect SQL** (DuckDB + Postgres): use `double precision` not `double`; avoid `median` (use `avg`).
  `ln`/`regr_slope`/`strpos`/`split_part`/`stddev_samp` work on both. Build `--target dev` AND `--target prod`.
- **The solver** must use damping — plain Jacobi oscillates on bipartite teammate pairs. Ratings are only
  comparable within the largest connected component.
- **Dagster asset modules**: no `from __future__ import annotations` (breaks context/resource introspection).
  `DbtCliResource` needs an explicit dbt executable path when the venv isn't on PATH (`definitions.py`).
- **FastF1 keys drivers by 3-letter code (VER)**, not Ergast `driver_id` — the laps/telemetry marts are
  keyed separately from the Jolpica marts; don't join them naively.
- **Evidence** DuckDB `connection.yaml` `filename` is relative to the source folder →
  `../../../data/warehouse/f1.duckdb`.

## Quality gates

`ruff` (line-length 100; selects E/F/I/UP/B/SIM/C4/RUF), `mypy` strict, `pytest`, and `sqlfluff` (dialect
duckdb, dbt templater) run via pre-commit and GitHub Actions (`.github/workflows/ci.yml`). The
`orchestration.*` module relaxes mypy generics — it's validated by `dagster definitions validate` instead.
Baseline: `dbt build` = 61/61 models on both targets, ruff + mypy clean, pytest green.
