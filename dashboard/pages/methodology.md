---
title: Can I Trust This Result?
max_width: 1600
---

<AppNav />

<PageHeader
    eyebrow="Data & methodology"
    title="Can I trust this result?"
    description="See exactly what each metric measures, how much evidence supports it and where interpretation must stop."
    accent="trust"
/>

<KeyInsight label="Short answer" tone="positive">
The dashboard publishes immutable, checksum-verified snapshots and exposes sample coverage. Results still describe the available data rather than proving causality.
</KeyInsight>

## Validation status — exploratory, not certified

The first external reference panel checks 16 selected cases from the 2025
Belgian and Italian Grands Prix against official F1 reports. On snapshot
`20260911-robust-estimates-v4`, 13 of 14 positive events match the exact lap;
all 14 match within one lap. Both explicitly annotated negative windows agree.
These are selected examples, **not a population accuracy score**. The annotations
are single-reviewer and have not been independently adjudicated.

One discrepancy remains visible: Piastri's Spa pass on Norris is assigned to
replay lap 4 instead of reported race lap 5.

A separate retrospective test trained an independent linear pace benchmark on
the first eight clean laps of each eligible stint. Across 5,239 later laps its
mean absolute error was **1.114 s**, worse than the training-median baseline's
**0.626 s**. This tests extrapolation risk, not the production estimator's
accuracy or the correctness of hypothetical pit strategies.

These results describe the named snapshot, not a continuously updated audit.
Coverage is incomplete, races were already inspected, and neither calibrated
uncertainty nor causal strategy claims have been validated.
[Read the protocol, sources, failures and remaining gates](https://github.com/denzlswaggin/f1-data-analytics/blob/main/docs/independent-validation.md).

### Additional source-agreement checks

On the same snapshot, 12 selected pit-stop windows in Bahrain and Imola 2025
cover 600 driver-laps. All 25 officially listed stops match exactly, with no
extra pit-entry detections in those windows. Four positive SC/VSC/red-flag
probes also match the reported lap.

These checks use official sources that may share timing provenance with the
app's inputs: they verify source agreement, **not independent sensor accuracy**.
Pit-table and narrative-report lap conventions can differ. They do not establish
global precision, accurate race-control effects or calibrated uncertainty.
[Read the window protocol and remaining limitations](https://github.com/denzlswaggin/f1-data-analytics/blob/main/docs/event-window-validation.md).

### Pass-sequence review: unresolved case

Three provisional pair windows now check event direction and order, with replay
coverage required for both drivers. Monza's lap 2 position return and lap 4 pass
match in order; no pass is detected in the selected Spa Leclerc/Verstappen window.

In Austria's lap 11, neither short lead exchange described by the race report
appears in the detector output. The reconstructed replay keeps Norris first
throughout that lap. The source descriptions and minimum pass duration still
need footage review: this is an **unresolved discrepancy**, not a proven detector
error. These provisional labels do not support a precision or accuracy score.
[Read the sequence protocol and finding](https://github.com/denzlswaggin/f1-data-analytics/blob/main/docs/pass-window-validation.md).

## What the rating means

The model compares teammates in the last qualifying segment both completed,
turns their time ratio into an additive log-pace gap, and solves the connected
teammate graph with regularisation. This reduces the largest shared car effect;
it does not remove upgrade timing, setup, traffic, reliability, injury, or every
change in teammate strength.

The career model answers “who was consistently fast relative to teammates?”.
The dynamic model answers “how did that relative form change by season?”. Its
90% intervals resample complete race weekends rather than treating mirrored
driver rows as independent observations.

## Published data contract

```sql snapshot
select * from f1.snapshot_metadata
```

<DataTable data={snapshot} rows=1>
    <Column id=version />
    <Column id=generated_at title="Published at" />
    <Column id=source title="Warehouse" />
    <Column id=latest_event_date title="Latest event" />
</DataTable>

```sql coverage
select section, race_label, sample_rows, entity_count, race_count, usable_samples,
       first_season, last_season, latest_event_date
from f1.data_coverage
order by section, race_label desc
```

<DataTable data={coverage} rows=50 download=true />

Every deployment consumes an immutable DuckDB snapshot. Its SHA-256 is checked
before the site builds, and the data contract blocks publication when required
ratings, strategy, telemetry, or replay partitions are missing. Coverage differs
by source because FastF1 telemetry is substantially heavier than Jolpica results.

For equations, validation and known limitations, see the
[model documentation](https://github.com/denzlswaggin/f1-data-analytics/blob/main/docs/dynamic-rating-model.md).

<RelatedAnalysis section="trust" current="methodology" />
