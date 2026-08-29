# Five-minute interview walkthrough

## 0:00–0:45 — Frame the problem

“I built an F1 data product to separate driver pace from shared car performance.
Instead of starting with a chart, I started with a comparison contract: teammates
in the last qualifying segment both completed. The result is useful only if I can
trace and reproduce every gap.”

Open the dashboard landing page. Point out the coverage card before the ranking:
sample size, races, seasons, latest event, and uncertainty are part of the
product, not footnotes.

## 0:45–1:45 — Trace one value

Use the eight-step path in the codebase guide:

```text
Jolpica/FastF1 → atomic Parquet partition → raw warehouse
→ dbt staging → teammate gap → Python solver → mart → Evidence
```

Mention why Python handles API/stateful work and graph/resampling algorithms,
while dbt owns relational transformation and testing. Show the Dagster asset
graph or dbt exposure to make the hand-offs concrete.

## 1:45–2:45 — Show reliability, not tool names

Describe one real failure mode: a historical telemetry correction previously did
not refresh an incremental mart. The fix was a durable touched-partition audit;
the mart now compares `source_loaded_at`, and a regression test mutates an old
row and verifies the correction without changing total row count.

Then show the production runbook commands:

```bash
f1-ingest health
f1-ingest restore-partition --resource telemetry --season 2026 --round 8
```

This demonstrates detection and recovery, not merely a green CI badge.

## 2:45–3:45 — Defend the model

Explain the static teammate graph first, then V2's driver-season nodes and
temporal edges. Lead with the holdout result: V2 improves only slightly (MAE
0.643 vs 0.645; direction 0.609 vs 0.606). Keeping both models is a product and
scientific choice—the stable benchmark answers career pace, V2 answers form.

Call out what the model does not control: upgrade timing, setup, reliability,
traffic, and changing teammate strength. The strongest answer to “is it causal?”
is “no; it is a regularised observational comparison with measured predictive
validity.”

## 3:45–4:30 — Quantify scope

- 20 seasons, 398 race weekends, 102 drivers, 8,168 directed qualifying gaps.
- 25 dbt models, 146 data tests, 3 unit tests, DuckDB/Postgres CI.
- 1,190 controlled race gaps across 92 races.
- 467 published driver-season V2 estimates with clustered intervals.

State that telemetry/replay is intentionally sample coverage in the current
warehouse; the UI exposes that rather than implying a complete archive.

## 4:30–5:00 — Close with the next decision

“My next model experiment would be joint qualifying/race partial pooling with a
final untouched test block. My next platform step would be managed Postgres and
versioned object storage plus an automated restore drill. I would choose between
them based on whether the immediate goal is analytical evidence or operational
ownership.”

## Likely follow-up questions

### Why not Spark or Kafka?

The sources are scheduled APIs and the dataset fits comfortably on one host.
Adding distributed infrastructure would increase operational surface without
solving a measured bottleneck. Partitioned Parquet and Postgres leave a clean
migration path if volume or latency changes.

### Why is the model not entirely in dbt?

The gap construction is relational and belongs in dbt. Iterative graph fitting,
bootstrap resampling, and race replay resampling are clearer and easier to test
as pure NumPy/pandas code. Dagster represents both as one lineage graph.

### What would break first at production scale?

The single-host volumes and synchronous bootstrap. Move the lake to object
storage, Postgres to a managed service, run compute workers separately, and
materialize bootstrap artifacts asynchronously. Do this after measuring runtime,
not pre-emptively.

### What result surprised you?

The model predicts direction better than chance but not exact single-session gap
magnitude, and V2's gain is tiny. Publishing those negative/weak results made the
project more credible and changed the product framing from “true skill” to a
teammate-normalised pace lens.
