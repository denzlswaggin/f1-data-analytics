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

**Status: all 5 milestones complete, plus two feature waves now merged to `main`.**
The **API expansion** added four marts — pit strategy, weather-adjusted
degradation, straight-line speed, and resampled telemetry — verified live on 2024
data (see "Further marts" below). The **animated race replay** added FastF1's
positional feed, a Python-built `marts.race_replay`, a custom Svelte track-map
component, a race-control feed, team-radio audio + transcripts, and a
season-spanning race picker (see "Race replay — animated track map" below). The
local Evidence dashboard runs at http://localhost:3000 via
`cd dashboard && npm run dev`.

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

## Race replay — animated track map (`feat/race-replay`, 2026 data)

A signature **interactive** feature: an animated map that replays a race with all
cars moving around the circuit at their true relative positions, with a timing
tower (order + gap to leader), play/pause, a scrubber, and a speed multiplier.
Built end-to-end on real **2026** data.

- **New raw source `raw.positions`** — FastF1's *positional* feed
  (`session.pos_data`), one row per car per sample on the shared `session_time_sec`
  clock: `(season, round, session, driver_code, session_time_sec, x, y, status)`.
  This is the missing **time axis** the distance-gridded `raw.telemetry` lacks —
  it's what lets every car be placed at the same instant. Ingest is heavy
  (~669k rows for one race at ~5 Hz). `clients/fastf1_client.py:load_session_position`
  + pure `thin_positions`; `pipeline.py:ingest_positions`; CLI `positions`; config
  `F1_FASTF1_POSITION_RATE_HZ` (default 5). `stg_positions` types it.
- **Data cleaning** (two layers). FastF1's positional feed is dirty:
  **(0,0) sentinels** ("no signal / in garage", ~9% of rows, still `status='OnTrack'`),
  **teleport** samples (implied speed >1000 m/s), and **retired cars** whose feed
  freezes at a parked point to the session end. Cleaned at (1) **ingest** — pure
  `clean_positions` drops (0,0) + teleports (implied speed >
  `F1_FASTF1_POSITION_MAX_SPEED_MPS`, default 300 — generous over the ~95 m/s
  physical max because position-derived speed is noisy ~180 m/s p99.9); and (2) the
  **replay builder** — `resample_race` retires a car when its position **stops
  changing** (last-movement detection, red-flag-safe since a car that resumes has a
  later last-movement), plus a tunable grace `F1_REPLAY_RETIRE_BUFFER_S` (default 5 s,
  CLI `--retire-buffer`), so retirees vanish where they pull off instead of freezing.
  A safety cap `F1_REPLAY_RETIRE_MAX_LINGER_S` (default 120 s) bounds this above — a
  retiree is never shown more than ~a lap past its last completed lap, guarding a
  recovered car whose sensor keeps moving. A dbt `expression_is_true` (x≠0 or y≠0)
  on `stg_positions` catches (0,0) regressions.
- **`marts.race_replay`** — built by **Python** (`analytics/replay.py`, like
  `driver_ratings` — *not* dbt). `resample_race` interpolates every car's x/y onto
  one uniform time grid (`--tick`, default 1 s), reconstructs per-car lap progress
  from lap timing to rank the field, and derives `gap_to_leader_s`/`gap_to_ahead_s`
  (invert the leader's progress curve by *first*-reached time; hold at the finishing
  margin once a car crosses the line; finish-order ties broken by line-crossing
  time). Grain: `(season, round, driver_code, t_s, x, y, running_order,
  gap_to_leader_s, gap_to_ahead_s)`. Kept lean — names/teams/colours join
  client-side. `build_race_replay(season, round)` (one race) /
  `build_race_replays(season, rounds)` (many, for the picker) → `replace_table`.
- **Team colours** — `warehouse/dbt/seeds/constructor_colors.csv` (FastF1 team name
  → hex), pinned to the `staging` schema.
- **Serving** — `dashboard/components/TrackMap.svelte` (auto-imported canvas
  component: static track layer + animated dots, browser-side interpolation between
  ticks), `pages/race-replay.md`, sources `race_replay.sql` (lean feed) +
  `race_replay_meta.sql` (tiny per-driver lookup).
- **Interactive** (`feat/replay-interactive`): the tower shows **interval to the car
  ahead** in F1 3-decimal format (`gap_to_ahead_s`); **click a car** (map or tower)
  to follow it (highlight + dim others); **hover** for a tooltip; **scroll to zoom /
  drag to pan** (single affine world→screen transform, non-passive wheel).
- **Race-control feed** (`feat/replay-interactive`): `raw.race_control` ←
  `load_session_race_control` (FastF1 `race_control_messages`; message times →
  session clock via `session.t0_date`, which needs a telemetry load but reads from
  cache). `ingest_race_control` / CLI `race-control` / `stg_race_control` (dedupes
  the feed's exact-duplicate messages, cross-dialect — no `QUALIFY`). Source
  `race_control.sql` aligns to `t_s`. The component shows a live **Race control**
  panel + a clickable **event-marker timeline** (safety cars / red flags / penalties
  / chequered) to jump to key moments.
- **Team radio** (`feat/replay-team-radio`): audio clips via **OpenF1**. The F1
  archive 403s the `TeamRadio` stream for 2026 (works for 2024), so use OpenF1:
  `clients/openf1.py` + `ingest_team_radio` maps `(season, round)`→OpenF1
  `session_key` by race date and aligns clip UTC times to the session clock via
  FastF1 `session_reference`/`t0_date` (driver code from num→code with filename
  fallback `_code_from_radio_url`). CLI `team-radio` / `stg_team_radio` / source
  `team_radio.sql` (in-race only) / Dagster `raw_team_radio`. Component: a 📻 marker
  lane (per-driver when a car is followed) — click to jump + **play the MP3**
  (`<audio>`), roll the replay on, and show a **transcript subtitle**.
  Coverage: OpenF1's 2026 is a sparse *broadcast* subset (~20–40/race, some drivers
  none); 2024 is far richer (~137/race, all drivers).
- **Transcripts** (`feat/replay-radio-transcripts`): from the public HF dataset
  `MikCil/f1-team-radio` (ASR over the radio archive, **2018–2025, no 2026**).
  `_load_hf_transcripts(season)` reads it via duckdb `hf://` and joins by
  `(racing_number, timestamp)` — exact match, one clip's driver+engineer rows
  concatenated — filling a `transcript` column on `raw.team_radio` (null for 2026).
- **Multi-season replay**: `build_all_replays()` / CLI `replay --all` builds a race
  for every `(season, round)` in `stg_positions`, so the picker spans seasons; the
  Evidence sources **year-prefix `race_name`** ("2024 Bahrain Grand Prix"). The 2024
  Bahrain GP is ingested as the transcript showcase (full radio + 104/107 transcripts).
- **Validated on 2026 Australian GP**: final top-12 match the official classification;
  gaps realistic (RUS win, ANT +3 s, …). Dagster: `raw_positions` + `race_replay`
  assets, both excluded-heavy `raw.positions` from the weekly job.

## File / module map

- `ingestion/` — EL package.
  - `config.py` (pydantic-settings, `F1_*` env, `.env`; incl. `fastf1_telemetry_resample_m`), `logging.py` (structlog).
  - `clients/jolpica.py` (rate-limited, retrying, paginating), `clients/fastf1_client.py` (lazy import; `load_session_laps` keeps speed traps + `lap_start_sec`, plus `load_session_weather`, `load_session_telemetry` + pure `resample_lap_telemetry`, `load_session_position` + pure `thin_positions`/`clean_positions`, `load_session_race_control`, and `session_reference` for `t0_date`), `clients/openf1.py` (tiny OpenF1 reader — team radio).
  - `resources.py` (season-scoped registry + flatteners races/results/qualifying; **per-round** flatteners `_flatten_pitstops`/`_flatten_ergast_laps`).
  - `loaders/lake.py` (Parquet), `loaders/warehouse.py` (idempotent-per-season load; `read_query`/`replace_table`).
  - `pipeline.py` (`ingest_resource`, `backfill`, `ingest_laps`, `ingest_pitstops`, `ingest_ergast_laps`, `ingest_weather`, `ingest_telemetry`, `ingest_positions`, `ingest_race_control`, `ingest_team_radio`, `season_rounds`), `cli.py` (`backfill`/`incremental`/`laps`/`pitstops`/`ergast-laps`/`weather`/`telemetry`/`positions`/`race-control`/`team-radio`).
- `analytics/` — `ratings.py` (pure solver + union-find), `replay.py` (pure `resample_race`), `pipeline.py` (`build_driver_ratings`, `build_race_replay`/`build_race_replays`), `cli.py` (`ratings`/`replay`).
- `warehouse/dbt/` — `profiles.yml` (dev=duckdb, prod=postgres), `macros/` (`generate_schema_name`, `parse_laptime`),
  `models/staging|intermediate|marts/*.sql` + `_*.yml` tests, `snapshots/drivers_snapshot.sql`.
- `orchestration/` — `assets.py` (raw.* assets keyed to dbt sources — `raw_pitstops`/`raw_ergast_laps`/`raw_weather`/`raw_telemetry`/`raw_positions`/`raw_race_control`/`raw_team_radio`, all `deps=[["raw","races"]]`; FastF1 assets ingest the current season *so far* via `season_rounds`; `@dbt_assets`, `driver_ratings`, `race_replay`),
  `definitions.py` (job + weekly schedule + `DbtCliResource`; the weekly job **excludes** `raw.telemetry`, `raw.positions`, `raw.race_control` **and `raw.team_radio`** — too heavy / cache-dependent to re-pull weekly, materialise on demand).
- `dashboard/` — Evidence project: `sources/f1/*.sql` (over the marts), pages `index.md`, `race-pace.md`, `pit-strategy.md`, `weather-and-speed.md`, `telemetry.md`, `race-replay.md`; `components/TrackMap.svelte` (auto-imported custom Svelte canvas component); `seeds/constructor_colors.csv`;
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
python -m ingestion.cli positions --season 2026             # FastF1 positions for the replay (heavy)
python -m ingestion.cli race-control --season 2026          # FastF1 race-control messages (uses telemetry cache)
python -m ingestion.cli team-radio --season 2026            # OpenF1 team-radio clips (partial coverage)
dbt build --project-dir warehouse/dbt --profiles-dir warehouse/dbt --target dev   # or --target prod
python -m analytics.cli ratings --top 20                    # solve + print leaderboard
python -m analytics.cli replay --season 2026                # build marts.race_replay (all completed rounds)
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
- **`raw.positions` is heavy too** (~669k rows/race at ~5 Hz) — also excluded from the weekly job. Two time axes coexist and must not be confused: `raw.telemetry` is per-lap by **distance** (no time), `raw.positions` is by **session time** (the replay's axis).
- **FastF1 pos_data (0,0) is a sentinel** ("no signal / in garage"), NOT a real track position — and it still carries `status='OnTrack'`, so you can't filter it by status; filter on the coordinates. Real on-track X/Y are offset (never exactly origin). Cleaned at ingest by `clean_positions`; a retired car then *parks* at a valid coord and its feed repeats to session end, so retirement is handled by **time** — vanish when the position stops changing (`resample_race`, tunable `F1_REPLAY_RETIRE_BUFFER_S`), not by coordinates.
- **Custom Evidence components** live in `dashboard/components/*.svelte` (auto-imported by filename; confirmed in the SDK) and pages compile to Svelte, so `<canvas>` + `requestAnimationFrame` works. But pages are **prerendered** on `evidence build` — any browser-only API (rAF, canvas) reachable from a top-level/`$:` reactive statement must be guarded (`typeof requestAnimationFrame === 'undefined'`), or the build 500s even though `npm run dev` (client render) is fine. `onMount` is safe (client-only).
- **Replay running order** is reconstructed from lap-progress; at the *exact* start (t=0) all cars share progress 0 so the tie-break order is cosmetic — it resolves the moment the race gets going. Cars with no lap data (early DNF) animate but don't appear in the tower.

## Remaining / future work

- Enable GitHub Pages (Settings → Pages → GitHub Actions) + run the *Deploy Dashboard* workflow for the public URL.
- **Backfill the new marts for real**: pit stops / ergast-laps over ~2011→current, and FastF1 weather/telemetry across a full season (the live check only ingested 2024 R1 for weather/telemetry). Likewise the **replay**: only 2026 + the 2024 Bahrain showcase are ingested — backfill more 2024 races (positions + radio) for a transcript-rich picker.
- Possible: a proper constructors/drivers dimension from the dedicated endpoints; driver-standings / championship-evolution mart; finer per-lap weather join (now that `lap_start_sec` is retained on `raw.laps`).
