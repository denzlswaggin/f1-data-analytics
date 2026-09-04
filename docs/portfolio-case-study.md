# Portfolio case study: an F1 data product, not just a dashboard

## Executive summary

This project turns fragmented Formula 1 timing sources into a reproducible data
product and asks one defensible analytical question: how much pace does a driver
show relative to teammates in the same machinery? It demonstrates the full data
lifecycle—source contracts, incremental ingestion, a recoverable lake, two
warehouse dialects, tested transformations, orchestration, model validation,
uncertainty, and a consumer-facing BI application.

On the current local dataset it covers 2006–2026, 411 completed race weekends,
103 drivers, and 8,424 directed qualifying comparisons. Race analysis adds 784
controlled teammate gaps across 60 races. The browser-facing snapshot includes
613,680 telemetry rows and 4,129,511 animated race-replay ticks across the races
whose heavy sources have been loaded.

## The user problem

Championship points mix driver skill, car strength, reliability, and team
strategy. A useful comparison must reduce the largest shared confounder without
claiming it has removed every bias. Teammates provide a natural within-car
comparison, and the last qualifying session both reached provides a consistent
measurement rule.

The output serves two audiences:

- an F1 analyst can explore career pace, season-specific form, race pace,
  strategy, telemetry, and replay;
- a data team can inspect lineage, tests, partition audits, failed runs, and the
  exact recovery path behind every published number.

## Architecture and key decisions

| Decision | Why it was chosen | Trade-off |
| --- | --- | --- |
| Python EL, dbt transforms | Keeps API/state logic in Python and relational business rules in SQL | Python-written marts need explicit Dagster lineage |
| DuckDB dev, Postgres prod | Fast zero-service iteration with a real server-database compatibility gate | Every SQL change must remain cross-dialect |
| Atomic Parquet partitions | Raw recovery source and cheap replay of one season/round | Local volumes need an off-host backup policy |
| Round/session replacement | Late corrections do not rebuild or overwrite a whole season | Partition metadata becomes part of the correctness contract |
| Dagster asset graph | Scheduling, durable run history, retries, and blocking checks in one view | A single-host Compose deployment is not horizontally scalable |
| Static rating plus V2 | Stable career benchmark remains comparable; V2 exposes changing form | V2's predictive improvement is deliberately reported as marginal |

## Reliability work

The first correctness pass fixed the failure modes that most often make a data
portfolio look good but behave badly:

1. Lake writes are atomic and partitioned by season/round/session.
2. Warehouse loads are idempotent and record `load_id`, timestamp, row count,
   and touched partition.
3. Late telemetry corrections rebuild only the audited race partition; a
   regression test mutates historical source data and proves propagation.
4. The current season derives from the calendar or an environment override.
5. Dagster checks block downstream publication when core loads are missing,
   stale, duplicated, null, or carry invalid intervals.
6. `restore-partition` repairs one warehouse partition directly from the lake.

The persistent deployment stores warehouse data and Dagster history in
Postgres, with durable volumes for lake, cache, and compute logs. The runbook
covers smoke checks, backup, incident triage, and restore drills.

## Transformation and quality evidence

The dbt project contains 27 models in staging, intermediate, and marts. Its CI
fixture runs 156 data tests and 3 unit tests against DuckDB and Postgres. Separate
gates run Ruff, mypy, pytest, SQLFluff, Dagster definition validation, Compose
validation, dbt documentation coverage, a targeted incremental-correction test,
dashboard data checks, and an Evidence strict build.

The public dashboard never silently substitutes zero rows. Each section shows
coverage—sample rows, entities, races, season range, and latest represented event
date—and labels descriptive metrics as descriptive rather than causal.

## Analytical result and honest boundary

The static regularised teammate graph predicts the winner of future qualifying
comparisons above chance. V2 adds driver-season nodes, temporal regularisation,
Q-session reliability weights, and a race-weekend cluster bootstrap. On the
current expanding-window evaluation:

| Model | MAE | Direction accuracy |
| --- | ---: | ---: |
| Static career benchmark | 0.638 | 0.605 |
| Dynamic latest-season model | 0.634 | 0.607 |

That is evidence of parity plus a small gain, not a breakthrough. V2 earns its
place because it answers a different product question—how form evolves—and its
uncertainty intervals make weak seasons visible. Neither model removes upgrades,
setup, reliability, traffic, or teammate-strength effects.

## What this demonstrates to a data team

- Data engineering: resilient clients, typed configuration, atomic lake writes,
  idempotent loaders, audit manifests, recovery, and persistent orchestration.
- Analytics engineering: layered dbt models, source contracts, unit/data tests,
  dual-dialect CI, documentation, and dashboard exposures.
- Data science: graph-based estimation, shrinkage, temporal validation,
  sensitivity analysis, clustered uncertainty, and explicit negative results.
- Product thinking: consumer questions, performance-aware marts, coverage UX,
  accurate language, operational ownership, and an interview-ready narrative.

## Next evidence worth adding

The highest-value next experiment is a joint qualifying/race hierarchical model
evaluated on a final untouched season block. The highest-value platform upgrade
is a managed Postgres plus versioned object storage deployment with an automated
restore drill. Neither should be claimed complete until its acceptance evidence
is public: calibration/backtest artifacts for the model and a successful restore
record plus uptime/freshness history for the platform.
