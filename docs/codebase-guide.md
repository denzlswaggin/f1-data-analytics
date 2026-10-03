# Codebase guide — understand it, then expand it

A from-scratch tour of how this platform works, written so you can read it next to
the code and confidently add your own features. It explains **what each layer
does, how the pieces connect, why the key design decisions were made, and how to
extend each layer**. Pair it with the top-level architecture in
[`../README.md`](../README.md) and the deep operational notes in the
`f1-platform` skill.

## Contents

1. [The one-paragraph mental model](#1-the-one-paragraph-mental-model)
2. [The end-to-end data flow (trace one number)](#2-the-end-to-end-data-flow-trace-one-number)
3. [Layer 1 — Ingestion (Python EL)](#3-layer-1--ingestion-python-el)
4. [Layer 2 — The warehouse & dbt](#4-layer-2--the-warehouse--dbt)
5. [Layer 3 — The signature insight (the rating solver)](#5-layer-3--the-signature-insight-the-rating-solver)
6. [Layer 4 — Orchestration (Dagster)](#6-layer-4--orchestration-dagster)
7. [Layer 5 — Serving (Evidence dashboard)](#7-layer-5--serving-evidence-dashboard)
8. [Cross-cutting concerns](#8-cross-cutting-concerns)
9. [How to add things (recipes)](#9-how-to-add-things-recipes)
10. [Glossary](#10-glossary)

---

## 1. The one-paragraph mental model

Raw F1 data enters through a **Python extract-load (EL) layer** that pulls from two
APIs, writes it to a **Parquet "lake"** on disk, and loads it into a **warehouse**
(DuckDB in dev, Postgres in prod). **dbt** then transforms the raw tables through
three layers — `staging → intermediate → marts` — each a schema in the warehouse.
The headline insight (cross-era driver ratings) is *not* a dbt model: it's a
**Python numpy solver** that reads a dbt intermediate table, solves a least-squares
problem, and writes the result back into the `marts` schema. **Dagster** can run
that whole chain on a schedule, and **Evidence** turns the marts into a web
dashboard. Everything is designed to run identically on DuckDB and Postgres, and
every load step is **idempotent** (safe to re-run).

```
Jolpica API ─┐
             ├─► ingestion/ (EL) ─► data/raw/*.parquet ─► warehouse: raw.*  ─┐
FastF1 ──────┘                                                               │
                                                                             ▼
                              dbt:  raw ─► staging ─► intermediate ─► marts (tables)
                                                          │
                          analytics/ratings.py solver ◄───┘ (reads int_teammate_quali_gaps)
                                     │ writes marts.driver_ratings
                                     ▼
                              Evidence dashboard  (dashboard/)
                          Dagster (orchestration/) can drive the whole thing on a schedule
```

Two systems write into the `marts` schema: **dbt** (the `mart_*` models) and
**Python** (`driver_ratings`, `driver_ratings_v2`, `driver_pace_profile`,
`race_replay`, and `race_overtakes`). Keep that distinction
in your head — it's the one part of the architecture that isn't "just dbt".

> **Newer feature — the animated race replay.** A second Python-built mart
> (`analytics/replay.py` → `marts.race_replay`) served by a custom Svelte canvas
> component (`dashboard/components/TrackMap.svelte`) on `pages/race-replay.md`. It
> resamples FastF1's time-stamped **positional** feed (`raw.positions` — unlike the
> distance-gridded `raw.telemetry`, this one carries a shared clock) so every car
> can be drawn at the same instant. Around that core it layers three new raw
> sources and their cleaning: the notoriously dirty positional feed (cleaned at two
> layers, see [§3](#3-layer-1--ingestion-python-el)), a **race-control** feed
> (`raw.race_control` — flags, safety cars, penalties), and **team-radio** audio
> with ASR **transcripts** (`raw.team_radio`, via OpenF1 + a Hugging Face dataset).
> The dashboard picker spans seasons (2026 + a 2024 showcase). This guide says
> where each piece lives and how to extend it; the `f1-platform` skill has the
> exhaustive write-up (every config knob, the cleaning thresholds, coverage caveats).

---

## 2. The end-to-end data flow (trace one number)

The best way to understand the system is to follow a single fact from API to
pixel. Take **Verstappen's qualifying time at the 2024 Bahrain GP**.

1. **Extract.** `ingestion/pipeline.py:extract_resource` asks
   `JolpicaClient.paginate` for the `qualifying` resource of season 2024. The
   client (`ingestion/clients/jolpica.py`) fetches pages of JSON, honouring rate
   limits and retries.
2. **Flatten.** Each nested race record is turned into flat rows by
   `_flatten_qualifying` in `ingestion/resources.py` — one dict per driver with
   `q1`/`q2`/`q3` as strings like `"1:29.708"`.
3. **Land in the lake.** `loaders/lake.py:write_parquet` writes the season's rows
   to `data/raw/qualifying/season=2024/data.parquet`.
4. **Load the warehouse.** `loaders/warehouse.py:load_dataframe` deletes any
   existing 2024 rows and inserts the new ones into `raw.qualifying` (idempotent).
5. **Stage.** dbt's `stg_qualifying.sql` casts types and calls the `parse_laptime`
   macro to turn `"1:29.708"` into `89.708` seconds (`q3_sec`).
6. **Compute the gap.** `int_teammate_quali_gaps.sql` pairs Verstappen with his
   teammate for that race and computes `pace_gap = 100 * (ln(t_ver) - ln(t_mate))`.
7. **Solve.** `analytics/ratings.py:compute_ratings` folds that gap (and thousands
   of others) into a single rating for every driver and writes `marts.driver_ratings`.
8. **Serve.** `dashboard/sources/f1/driver_ratings.sql` selects from that mart, and
   `dashboard/pages/index.md` renders it as a bar chart and table.

Every feature you add will slot into one (or a few) of these eight steps.

---

## 3. Layer 1 — Ingestion (Python EL)

**Package:** `ingestion/`. **Job:** get raw data from the outside world onto disk
and into the warehouse, reliably and idempotently. It's plain Python — no framework.

### The pieces

| File | Responsibility |
|---|---|
| `config.py` | All configuration as a pydantic-settings `Settings` object (env vars prefixed `F1_`, or `.env`). One source of truth for the warehouse target, paths, API URL, rate limits. |
| `logging.py` | `structlog` setup — every log line is structured (`log.info("event.name", key=val)`). |
| `clients/jolpica.py` | HTTP client for the Jolpica/Ergast API: rate-limited, retrying (tenacity), and paginating. |
| `clients/fastf1_client.py` | Wraps the FastF1 library for per-lap telemetry, plus weather, the time-stamped **positional** feed (`load_session_position` + pure `thin_positions`/`clean_positions`) and race-control messages. Imported lazily (it's a heavy optional dependency). |
| `clients/openf1.py` | Tiny reader for the **OpenF1** API — used only for team-radio audio clips (the one thing FastF1/Ergast don't expose for the current season). |
| `resources.py` | A **declarative registry** of what can be ingested and how to flatten it. |
| `loaders/lake.py` | Writes DataFrames to the partitioned Parquet lake. |
| `loaders/warehouse.py` | Loads DataFrames into the warehouse (DuckDB or Postgres), idempotently. |
| `pipeline.py` | Ties it together: `extract_resource`, `ingest_resource`, `backfill`, and the dedicated per-round/per-source ingests (`ingest_laps`, `ingest_positions`, `ingest_race_control`, `ingest_team_radio`, …). |
| `cli.py` | The `python -m ingestion.cli ...` command-line entrypoint (Typer). |

### The key design idea: a declarative resource registry

Instead of a bespoke function per endpoint, `resources.py` defines a small
`Resource` dataclass (`name`, `path_template`, `table_key`, `list_key`,
`flatten`) and a `RESOURCES` dict holding one entry each for `races`, `results`,
and `qualifying`. A **flattener** is a function that takes one nested API record
plus the season and yields flat row-dicts.

This is why adding a new season-scoped endpoint is a copy-paste-and-adapt job
(see [recipe 9.1](#91-add-a-new-ingestion-resource)): the generic
`extract_resource` loop already knows how to page any resource and call its
flattener.

**Per-round endpoints** (Ergast pit stops and lap positions; FastF1 weather and
telemetry) are scoped by `{season}/{round}` and so *don't* fit that season-only
registry. They get a dedicated `ingest_*` in `pipeline.py`
(`ingest_pitstops`, `ingest_ergast_laps`, `ingest_weather`, `ingest_telemetry`)
that loops the requested rounds, writes one lake partition per round/session,
and replaces only those rounds in the warehouse. `season_rounds()` reads `raw.races` to
supply the round list (dates ≤ today for a "season so far" backfill).

### Cleaning at ingest (new: the race-replay sources)

The **race replay** adds three raw sources that don't come from Ergast — FastF1's
positional feed (`raw.positions`, the *time* axis the replay animates on), FastF1
race-control messages (`raw.race_control`), and OpenF1 team-radio clips
(`raw.team_radio`, later enriched with ASR transcripts from a public Hugging Face
dataset) — each with a dedicated `ingest_*` in `pipeline.py`.

The positional feed is unusually dirty, which introduces a concept this layer
didn't have before: **cleaning at ingest**. `clean_positions` (pure, unit-tested)
drops FastF1's `(0,0)` "no-signal / in-garage" sentinels and physically-impossible
"teleport" samples *before* they land, so `raw.positions` stays faithful to a real
car on track. (The usual rule still holds — staging never filters rows — so this
one dirty *source* is scrubbed upstream instead. A car that **retires** parks at a
*valid* coordinate, which is a temporal problem, not a bad coordinate, so that case
is handled downstream by the replay builder, keyed on time; the skill has the full
story.)

### The idempotency contract (important)

Re-running a backfill must never duplicate or corrupt data. Two mechanisms
enforce this:

- **Lake:** season-grain resources atomically replace `season=<n>/data.parquet`;
  high-volume sources atomically replace only their
  `season=<n>/round=<r>/session=<s>` file.
- **Warehouse:** season resources use delete-then-insert per season; round-grain
  resources delete only the rounds present in the incoming frame. Every success
  updates `raw.ingestion_partitions`, which drives targeted late-data refreshes.
  `tests/test_warehouse.py` locks these behaviours in.

`warehouse.py` also exposes helpers used elsewhere: `read_query(sql)` (run a
read-only query, get a DataFrame back) and `replace_table(df, schema, table)`
(fully replace a non-partitioned table — used to write `marts.driver_ratings`).
`replace_table_partition(...)` atomically deletes and inserts one exact mart
partition on DuckDB and Postgres; the scheduled replay/overtake builders use it
so round 12 can be corrected without rebuilding rounds 1–11.

### Round-level orchestration

`orchestration/round_refresh.py` is the unattended production path. Its Dagster
job has a multi-dimensional `season × round_session` partition (for example
`2026 × 8:R`; Dagster permits two dimensions) and performs a
strict sequence: refresh the small season endpoints, ingest one race partition,
run dbt, then incrementally materialize that race's replay and overtakes. The
Monday schedule resolves only the latest race dated before today; the same job
can be launched for any explicit partition as a targeted backfill. Season asset
jobs remain available for broad historical backfills.

Every stage is timed and exposes duration/budget/utilisation metadata. The
budget settings live in `Settings`, making performance drift a visible failed
run instead of an unnoticed growth in weekly batch time.

### The client robustness pattern

`JolpicaClient` is the reference for "polite" API access, worth studying:
a `_RateLimiter` enforces a minimum interval between requests; `_request` is
wrapped in a tenacity `@retry` that backs off on 429/5xx/connection errors and
honours the `Retry-After` header; `paginate` follows Ergast's `limit`/`offset`
pages until it has everything. (The FastF1 client is deliberately thinner — a good
first hardening exercise is to bring it up to this standard.)

---

## 4. Layer 2 — The warehouse & dbt

**Directory:** `warehouse/dbt/`. **Job:** turn messy `raw.*` tables into clean,
tested, analysis-ready tables using SQL.

### Warehouse targets and schemas

`profiles.yml` defines two targets that run the *same models*:
`dev` (DuckDB, a single file at `data/warehouse/f1.duckdb`) and `prod`
(Postgres via docker-compose). `dbt_project.yml` sets the materialisation and
schema per layer:

| Layer (folder) | Materialised as | Schema |
|---|---|---|
| `models/staging/` | **view** | `staging` |
| `models/intermediate/` | **view** | `intermediate` |
| `models/marts/` | **table** | `marts` |

Staging/intermediate are views (cheap, always fresh); marts are physical tables
(fast to query from the dashboard). The `generate_schema_name` macro
(`macros/generate_schema_name.sql`) forces the schema names to be *exactly*
`staging`/`intermediate`/`marts` on both targets, rather than dbt's default of
prefixing them — so `analytics/pipeline.py` can hard-code `intermediate.` /
`staging.` prefixes and have them work everywhere.

### The three layers, by example

- **staging** (`stg_*.sql`): one model per raw source. Cast types, rename, add a
  surrogate key. No joins, no business logic. E.g. `stg_qualifying.sql` parses
  Q1/Q2/Q3 strings to seconds via the `parse_laptime` macro; `stg_results.sql`
  types the finishing data and derives an `is_classified` flag. `stg_drivers` /
  `stg_constructors` are dimensions derived from `stg_results` by aggregation
  (there's no dedicated drivers endpoint ingested).
- **intermediate** (`int_*.sql`): the reusable business logic. There's one, and
  it's the heart of the project: `int_teammate_quali_gaps.sql` (see
  [section 5](#5-layer-3--the-signature-insight-the-rating-solver)).
- **marts** (`mart_*.sql`): the final, dashboard-facing tables:
  `mart_driver_season_pace` (per-driver-per-season teammate summary),
  `mart_lap_times` (green-flag race laps with tyre context, FastF1),
  `mart_tyre_degradation` (pooled tyre fall-off per race/compound), and
  `mart_stint_degradation` (per-stint fall-off). Plus the season-grain bridge
  `stg_driver_codes` that lets the FastF1 marts join the Ergast driver dimension.
  The API-expansion work (PR #8) adds four more: `mart_pit_strategy`
  (undercut/overcut per stop, Ergast), `mart_weather_degradation` (fall-off by a
  race-day weather bucket), `mart_speed_trap` (straight-line speed), and
  `mart_lap_telemetry` (distance-resampled car telemetry for speed traces + a
  track map) — each with its own `stg_*` model and `raw.*` source.

The **race replay** adds three *staging-only* models — `stg_positions`,
`stg_race_control`, `stg_team_radio` — that type and clean its new raw sources.
There is deliberately **no `mart_*` model** for the replay: the mart itself
(`marts.race_replay`) is built in Python, not SQL, because resampling every car
onto one time grid is far easier in numpy/pandas (same reason the ratings mart is
Python — see [recipe 9.3](#93-add-a-python-analytics-transform)). So these staging
models are consumed by `analytics/replay.py`, not by a downstream dbt model.

### Tests and the snapshot

Tests live in `_*.yml` files next to the models (`unique`, `not_null`,
`relationships`, plus `dbt_utils` package tests). CI loads a committed race
fixture and runs the complete `dbt build` on both DuckDB and Postgres, including
data and unit tests. The DuckDB leg also generates the lineage catalog and runs
the late-telemetry-correction regression.

`snapshots/drivers_snapshot.sql` is a slowly-changing-dimension snapshot: as the
season progresses and a driver's `last_season`/`race_entries` change, dbt records
each change with `dbt_valid_from`/`dbt_valid_to` timestamps.

### The cross-dialect rule (memorise this)

Every model must run on **both** DuckDB and Postgres. In practice: use
`double precision` (not `double`); avoid `median` (use `avg`); `ln`, `regr_slope`,
`strpos`, `split_part`, `stddev_samp` are safe on both. Any Postgres-only feature
(e.g. an index) goes behind `{% if target.type == 'postgres' %}` — see the
`post_hook` in `mart_lap_times.sql`. **Always build both targets** before calling
a SQL change done.

---

## 5. Layer 3 — The signature insight (the rating solver)

This is the intellectual core. Read `int_teammate_quali_gaps.sql` and
`analytics/ratings.py` together with this section.

### The idea

Teammates drive **identical cars**, so the qualifying gap *between two teammates*
is a clean measurement of driver skill with the car cancelled out. But that only
compares each driver to *their* teammate. To build one cross-era leaderboard, you
chain the pairwise gaps across the whole "teammate graph" (Hamilton is comparable
to Verstappen because Hamilton→Rosberg→Bottas→Russell→Verstappen are all linked by
shared teammates).

### Step 1 — the gap (SQL, `int_teammate_quali_gaps.sql`)

For every race, the model:
1. keeps only teams that fielded exactly two cars (so each driver has one
   unambiguous teammate);
2. self-joins to pair the two teammates;
3. picks the **last knockout session both drivers set a time in** (Q3 if both
   reached it, else Q2, else Q1) — the fair, apples-to-apples comparison;
4. computes the gap as an **additive log-pace difference**:

   ```
   pace_gap = 100 * ( ln(driver_time) - ln(teammate_time) )
   ```

Why log? It makes the gap **antisymmetric** (`gap_ab = -gap_ba`) and **additive**
along a chain, and roughly a *percentage* difference (× 100). Positive = the
driver was slower. That additivity is exactly what lets the next step chain gaps
across drivers who never shared a car.

### Step 2 — the solve (Python, `analytics/ratings.py`)

We want one number per driver — a **pace deficit** `d_i` (lower = faster) — that
best explains every observed gap. Formally, minimise the sum of squared errors:

```
minimise   Σ over comparisons ( d_i − d_j − gap_ij )²
```

This is a **Massey-style least-squares rating** on the teammate graph. Solving the
normal equations gives a simple fixed-point: each driver's deficit should equal
the *average* of `d_teammate + gap` over all their comparisons. The code iterates
that to convergence. Three details make it robust:

- **Damped Jacobi iteration** (`damping = 0.5`). The naive update
  `d_i ← mean(d_j + gap_ij)` oscillates forever on a two-driver pair (A and B just
  swap values each step). Under-relaxing — `new = (1−λ)·old + λ·target` — kills the
  oscillation and guarantees convergence. This is the single most important line;
  see `ratings.py:131`.
- **Empirical-Bayes shrinkage** (`prior_weight = 8.0`). A ridge term adds
  `prior_weight` "pseudo-comparisons at rating 0" to each driver's denominator, so
  drivers with very few teammate races are pulled toward the field mean instead of
  topping the board on noise. Set `prior_weight = 0` for the pure fit (the tests
  do this to check exact recovery).
- **Connected components** (`_UnionFind`). The fit is only meaningful within a
  connected part of the teammate graph, and is identified only up to an additive
  constant. So the solver keeps the **largest connected component** and centres it
  (mean 0). Ratings are *not* comparable across different components.

The output is a DataFrame of `driver_id, n_comparisons, pace_deficit,
rating (= −pace_deficit, so higher = faster), rank`. `analytics/pipeline.py:build_driver_ratings`
wraps the solver: it reads the gaps and the driver dimension via `read_query`,
enriches with names/nationality/season-span, and `replace_table`s the result into
`marts.driver_ratings`. (`tests/test_analytics_pipeline.py` covers this end to end.)

### The honest caveats (worth understanding)

The metric measures **margin over teammate**, not absolute speed — which is why a
driver with consistently strong teammates (Hamilton: Alonso, Rosberg, Russell) can
land mid-pack. Thin-sample drivers are shrunk. Cross-component comparisons are
invalid. These aren't bugs; they're the honest limits of the method, and being
able to explain them is what makes it a good portfolio piece.

### The second insight — tyre degradation

Lower-stakes but a nice contrast. `mart_tyre_degradation` fits
`regr_slope(lap_time, tyre_life)` over green-flag laps per race/compound — the pace
lost per lap of tyre age. `mart_stint_degradation` does the same at the finer
per-driver-per-stint grain. (Note the per-stint means are outlier-sensitive on
small samples; summarise by median when eyeballing.)

---

## 6. Layer 4 — Orchestration (Dagster)

**Directory:** `orchestration/`. **Job:** express the whole pipeline as a graph of
**assets** and run it on a schedule.

- `assets.py` defines the graph. The ingestion steps are `@asset`s keyed
  `["raw", "races"]`, `["raw", "results"]`, etc. — **the same names as the dbt
  sources**. `dbt_assets` then loads the dbt project and, via the custom
  `F1DbtTranslator`, maps each dbt source to those same `["raw", <name>]` keys, so
  dagster-dbt automatically wires the dbt models *downstream* of the ingestion
  assets. The `driver_ratings` asset declares `deps` on the dbt intermediate model
  and the driver dimension, closing the loop from ingest → dbt → solver.
- `definitions.py` assembles the `Definitions` (assets + a `refresh_pipeline` job
  selecting `*` + a Monday-morning `race_weekend_schedule` + the `DbtCliResource`).
  `_dbt_executable()` locates the dbt binary even when the venv isn't on `PATH`.

Two gotchas live here: Dagster asset modules must **not** use
`from __future__ import annotations` (it breaks Dagster's type introspection —
note `assets.py` has no such import), and the CI "orchestration" job validates the
graph with `dagster definitions validate` rather than running it.

You mostly won't touch this layer to add analysis — but any new dbt model
automatically becomes part of the `dbt_assets` graph, and any new ingestion
resource you want scheduled needs a matching `@asset` here.

---

## 7. Layer 5 — Serving (Evidence dashboard)

**Directory:** `dashboard/`. **Job:** a "BI-as-code" website built from SQL +
Markdown, with no separate BI tool.

- `sources/f1/connection.yaml` points Evidence at the DuckDB file
  (`../../../data/warehouse/f1.duckdb`, relative to the source folder).
- `sources/f1/*.sql` are named queries over the marts (e.g. `driver_ratings.sql`
  selects `marts.driver_ratings`). Evidence runs these and exposes them as tables
  named `f1.<file>` (e.g. `f1.driver_ratings`).
- `pages/*.md` are the pages. A page mixes Markdown with fenced SQL blocks (each
  named, e.g. ` ```sql top_drivers `) and Svelte-like components
  (`<BarChart>`, `<DataTable>`, `<Dropdown>`, `<LineChart>`). Inputs are reactive:
  the driver `<Dropdown>` on `index.md` feeds `${inputs.driver.value}` straight
  into the next SQL block, so selecting a driver re-runs the query.
- **Custom components.** Beyond Evidence's built-ins you can drop a Svelte file in
  `dashboard/components/` and Evidence auto-imports it by filename. The race replay
  uses this: `TrackMap.svelte` is a `<canvas>` animation (static track layer +
  per-tick interpolated dots, click-to-follow, scroll-zoom/drag-pan, a live
  race-control panel, and a 📻 team-radio lane that plays the clip audio with a
  transcript subtitle). Its `race-replay.md` page has a season picker spanning 2026
  and a 2024 showcase. **Gotcha:** pages are *prerendered* at `evidence build`, so
  any browser-only API (`canvas`, `requestAnimationFrame`, `window`) reachable from
  top-level or a `$:` reactive statement must be guarded, or the build 500s even
  though `npm run dev` (client render) is fine — put it in `onMount` or behind a
  `typeof … === 'undefined'` check.

Run it locally with `cd dashboard && npm run dev` (serves at
`localhost:3000/f1-data-analytics/`). `evidence.config.yaml` sets the project-site
base path for deployment.

---

## 8. Cross-cutting concerns

- **Configuration.** Everything configurable lives on the `Settings` object
  (`ingestion/config.py`), read from `F1_*` env vars / `.env`. The most important
  is `F1_WAREHOUSE=duckdb|postgres`, which flips every load and read between the
  two backends. Pass a `Settings` explicitly into functions to test them (as the
  tests do) — this dodges the `lru_cache` on `get_settings()`.
- **Idempotency.** Re-running anything is safe: parquet partitions overwrite,
  warehouse loads delete-then-insert per season or round, global marts fully
  replace, and replay/overtake marts replace only the requested race.
- **Cross-dialect SQL.** The single biggest source of "works in dev, breaks in
  prod" bugs. See [section 4](#the-cross-dialect-rule-memorise-this).
- **Testing.** Python tests in `tests/` (`pytest`) run in CI with only the `.[dev]`
  extra (`duckdb` is a core dep, so warehouse/solver tests work with no Postgres).
  dbt data tests run locally. `make check` runs ruff + mypy(strict) + pytest.
- **Dependency management.** dbt has strict transitive pins and is installed as a
  *separate* extra (`.[dbt]`) from the core; installing everything in one `pip`
  resolve overflows the resolver. mypy is pinned `<2` for the same dbt-compat
  reason. (This is why CI installs extras in separate steps.)

---

## 9. How to add things (recipes)

Each recipe names the files to touch and how to verify. These map onto the
practice exercises — build them yourself; the verification loop is your safety net.

### 9.1 Add a new ingestion resource

*Goal: pull a new season-scoped Ergast endpoint (e.g. `driver_standings`).*
1. In `ingestion/resources.py`, write a `_flatten_<name>(record, season)` generator
   (copy `_flatten_results` and adapt to the endpoint's JSON shape).
2. Add a `Resource(...)` entry to the `RESOURCES` dict (set `path_template`,
   `table_key`, `list_key`). Add it to `DEFAULT_RESOURCES` if it should backfill by
   default.
3. **Verify:** `python -m ingestion.cli backfill --season 2024 --resource <name>`,
   then check `raw.<name>` exists in the warehouse.
4. To surface it downstream, add a `stg_<name>.sql` + a source entry in
   `models/staging/_f1__sources.yml`, and (optionally) a `@asset` in
   `orchestration/assets.py`.

> Note: endpoints that are **per-round** (like pit stops) don't fit the
> season-scoped `Resource` pattern. Add an `ingest_<name>` in `pipeline.py` that
> loops rounds into one season frame and loads once, mirroring `ingest_laps` —
> see the existing `ingest_pitstops` / `ingest_ergast_laps` / `ingest_weather` /
> `ingest_telemetry`. Adding **columns** to a raw table you've already loaded
> (e.g. the speed-trap columns on `raw.laps`) means dropping and re-ingesting it
> once: DuckDB's `CREATE TABLE IF NOT EXISTS` won't add them and the positional
> INSERT then mismatches.

### 9.2 Add a new dbt mart

*Goal: a new analysis table from data you already have (e.g. grid-vs-finish).*
1. Create `models/marts/mart_<name>.sql` selecting from the relevant `stg_*`
   models (e.g. `stg_results` has `grid_position`, `finish_position`, `status`).
2. Add the model + tests to `models/marts/_marts__models.yml`
   (`unique_combination_of_columns`, `not_null`, ranges via `dbt_expectations`).
3. **Verify:** `dbt build --project-dir warehouse/dbt --profiles-dir warehouse/dbt --target dev`
   (then `--target prod` if Postgres is up). Keep the SQL cross-dialect.

### 9.3 Add a Python analytics transform

*Goal: a computed table that's easier in numpy/pandas than SQL (like the ratings).*
1. Put the pure logic in a module under `analytics/` (take `ratings.py` as the
   template: pure function, typed, unit-testable with no warehouse).
2. Add a `build_<name>` in `analytics/pipeline.py` that `read_query`s its inputs
   and `replace_table`s its output into `marts`.
3. Expose it as a CLI verb in `analytics/cli.py` (copy the `ratings` command).
4. **Verify:** a `tests/test_<name>.py` seeding a temp DuckDB (copy
   `tests/test_analytics_pipeline.py`), then run the CLI end to end.

### 9.4 Add a dashboard page

1. Create `dashboard/pages/<name>.md`. Add named SQL blocks over the marts and
   components (`<BarChart>`, `<DataTable>`, `<Dropdown>` — copy patterns from
   `pages/index.md` and `pages/race-pace.md`). If you need a new query, add a
   `sources/f1/<name>.sql`.
2. **Verify:** `cd dashboard && npm run dev` and open the page.

### 9.5 Add a custom (animated / interactive) component

*Goal: a visualisation Evidence's built-ins don't cover — like the replay track map.*
1. Add `dashboard/components/<Name>.svelte`; Evidence auto-imports it by filename, so
   you use it in a page like any built-in: `<Name data={my_query} ... />`.
2. Feed it a **lean** query — the whole result ships to the browser, so aggregate and
   trim server-side. (The replay keeps names/colours out of its big per-tick feed and
   joins them client-side from a tiny separate meta source.)
3. **Guard browser-only APIs** (`canvas`, `requestAnimationFrame`, `window`): they
   must not run at module top-level or in a `$:` statement, or `evidence build`
   (which prerenders each page) 500s. Use `onMount` or a `typeof … === 'undefined'`
   check.
4. **Verify:** `npm run dev` to iterate, then `npm run build` once to confirm the
   prerender doesn't crash (dev is client-rendered and won't catch it).

### 9.6 Add a new (non-Ergast) raw source

*Goal: ingest something the season-scoped registry can't express — a different API,
or a feed that needs cleaning (like the replay's positional data).*
1. Add a client under `ingestion/clients/` (copy `openf1.py` for a small REST reader,
   or extend `fastf1_client.py`). Keep any row-shaping in a **pure, testable**
   function (e.g. `clean_positions`) so it can be unit-tested without the network.
2. Add an `ingest_<name>` in `pipeline.py` that fetches, cleans, lands in the lake,
   and loads once per season (mirror `ingest_positions` / `ingest_team_radio`), plus
   a CLI verb and — if it should be scheduled — an `@asset` in `orchestration/`.
3. Add a `stg_<name>.sql` + a source entry so dbt (or a Python transform) can consume
   it. Remember the convention: **staging doesn't filter rows** — if the source is
   dirty, clean it at ingest (step 1), not in staging.
4. **Verify:** run the ingest, confirm `raw.<name>` and `stg_<name>` look right, then
   `dbt build --select stg_<name>` on both targets.

---

## 10. Glossary

- **EL / ELT** — Extract-Load(-Transform). We extract+load with Python, then
  transform in the warehouse with dbt.
- **Lake** — the on-disk Parquet files under `data/raw/`, partitioned by season.
- **Warehouse** — the queryable database: DuckDB (dev) or Postgres (prod).
- **Staging / intermediate / marts** — dbt's three transformation layers (clean →
  business logic → dashboard-facing).
- **Mart** — a final, consumer-facing table.
- **Surrogate key** — a hash of natural keys (`generate_surrogate_key`) used as a
  stable row/table id.
- **Teammate gap** — the log-pace qualifying difference between two teammates; the
  atomic unit of the rating.
- **Pace deficit / rating** — the solved per-driver number; `rating = −deficit`, so
  higher = faster.
- **Massey rating** — a least-squares rating that solves all pairwise comparisons
  jointly.
- **Damped Jacobi** — the iterative solver method; under-relaxed to converge.
- **Shrinkage (empirical Bayes)** — pulling low-sample estimates toward the mean.
- **Connected component** — a set of drivers linked by shared teammates; ratings
  only compare within one.
- **Idempotent** — safe to run repeatedly with the same result (no duplicate data).
- **Asset (Dagster)** — a node in the pipeline graph that produces a data artifact.
- **Cross-dialect** — SQL that runs identically on DuckDB and Postgres.
- **Positional feed** — FastF1's time-stamped car X/Y (`raw.positions`), the shared
  clock the race replay animates on; distinct from the distance-gridded
  `raw.telemetry`, which carries no time axis.
- **Race replay** — the second Python-built mart (`marts.race_replay`): every car
  resampled onto one uniform time grid so the whole field can be drawn at the same
  instant, served by the `TrackMap.svelte` canvas component.
