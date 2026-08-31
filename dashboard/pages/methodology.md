---
title: Can I Trust This Result?
---

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
