---
title: Can I Trust This Result?
hide_title: true
max_width: 1600
---

<AppNav />

<PageHeader
    eyebrow="Data & methodology"
    title="Can I trust this result?"
    description="See exactly what each metric measures, how much evidence supports it and where interpretation must stop."
    accent="trust"
/>

<KeyInsight label="Recorded results and model estimates">
Checksums and pipeline tests establish data integrity, not event accuracy.
Recorded classifications follow their source; racecraft events, reconstructed
gaps and strategy estimates remain model outputs with incomplete external validation.
</KeyInsight>

```sql snapshot
select * from f1.snapshot_metadata
```

<SnapshotStatus data={snapshot} />

## Current analytical evidence

```sql current_evidence
select analysis, candidates, eligible, unit, races,
    eligible * 100.0 / nullif(candidates, 0) as eligible_pct,
    limitation, validation_status
from f1.evidence_summary order by analysis
```

```sql evidence_export
select distinct snapshot_version, snapshot_sha256, methodology_version
from f1.evidence_summary
```

```sql validation_evidence
select evidence_type, status, report_date, evaluated_snapshot, evaluated_sha256, result, scope
from f1.validation_evidence
order by case evidence_type when 'Structural checks' then 1 when 'Predictive diagnostic' then 2
    when 'Source agreement' then 3 else 4 end
```

These counts are regenerated from the published snapshot. “Eligible” has a
different definition and unit for each analysis; percentages must not be averaged
into a trust score. Input race counts describe coverage, not independent samples.
Aggregate-only tables have no input race count here.

<div style="overflow-x: auto; max-width: 100%;">
<DataTable data={current_evidence} rows=15 download=true>
    <Column id=analysis title="Analysis" />
    <Column id=candidates title="Candidates" />
    <Column id=eligible title="Eligible" />
    <Column id=unit title="Counting unit" />
    <Column id=eligible_pct title="Eligible (%)" fmt="0.0" />
    <Column id=races title="Input races" />
    <Column id=limitation title="Interpretation limit" />
</DataTable>
</div>

### Validation evidence and its scope

Passing publication checks establishes consistency with the stated rules.
Historical diagnostics keep their original evaluated snapshot and report date;
they are never relabelled as current accuracy results. Missing or unmatched
artifacts are marked “Not evaluated for this snapshot.” A dated source-agreement
panel is not an independent footage review.

<div style="overflow-x: auto; max-width: 100%;">
<DataTable data={validation_evidence} rows=4>
    <Column id=evidence_type title="Evidence type" />
    <Column id=status title="Current snapshot status" />
    <Column id=report_date title="Check time / historical report date" />
    <Column id=evaluated_snapshot title="Evaluated snapshot" />
    <Column id=result title="Recorded result" />
    <Column id=scope title="Scope" />
</DataTable>
</div>

<ExpandableSection title="Evidence export provenance">
<div style="overflow-x: auto; max-width: 100%;">
<DataTable data={evidence_export} rows=1 />
<DataTable data={validation_evidence} rows=4>
    <Column id=evidence_type />
    <Column id=evaluated_sha256 title="Evaluated database SHA-256" />
</DataTable>
</div>
</ExpandableSection>

## Start with the evidence type

[Metric definitions](#metric-definitions) · [Uncertainty and missing data](#uncertainty-and-missing-data) · [Validation status](#validation-status) · [Published data contract](#published-data-contract)

1. **Source observations:** recorded classification, lap timing, messages,
   weather and radio. Coverage and clock alignment can still be incomplete.
2. **Derived comparisons:** teammate ratings, peer-relative pace, stint trends,
   technique profiles and detected passes. Filters define which observations enter.
3. **Counterfactual estimates:** pit-timing scenarios and neutralised pit savings.
   These require extra assumptions and do not attribute the final race result.
4. **Animation:** replay motion and pit-lane paths interpolate or project sampled
   data. The displayed path does not verify a physical overtake or racing line.

## Metric definitions

A sample count is meaningful only with its unit. Driver laps within a race,
mirrored teammate comparisons and replay ticks are correlated observations.

<div style="overflow-x: auto; max-width: 100%;">

| Analysis | What the value means | Publication evidence | Main limitation |
| --- | --- | --- | --- |
| Ratings / Driver Comparison | Higher fitted qualifying rating means faster within the teammate network | Career display: at least 40 directed comparisons; season estimates show their counts and 90% intervals | Shared years are not identical weekends or direct head-to-heads; car effects remain |
| Saturday vs Sunday | Difference between fitted qualifying and race ratings | Joint weekend resampling within seasons; interval needs at least 900 valid draws out of 1,000 | Correlated estimates require joint resampling; this is not a finish prediction |
| Race Pace / Traffic | Seconds relative to the median of other drivers on the same lap and compound; lower is faster | At least three other peers; clean-air summary needs five clean laps; traffic association also needs five matched traffic laps | Tyre age, car and context differ; replay gaps can be estimated |
| Pace Consistency | Robust residual spread in seconds after a stint trend; lower is more repeatable | Valid clean-air stint fits and at least eight modelled laps per driver | Slow-tail cost is unexplained residual time, not a count of driver mistakes |
| Tyre Warmup | Seconds relative to the later mature trend; confirming lap of two consecutive laps within +/-0.50 s | Clean-air reference and complete history through the confirming pair | A fully observed six-lap window without confirmation is a >6 bound; gaps remain unknown |
| Driver DNA | Robust standardised technique differences on selected teammate lap pairs | Same dry compound, green track, race-lap and tyre-age gaps at most three; at least 100 common points and 95% valid coverage | Selected fast laps are not a full-race technique census; mirrored rows are one pair |
| Track Fit | Difference in technique profile by inferred track archetype | At least five eligible races per driver/archetype; 90% race-bootstrap interval | Snapshot-level archetype thresholds and small samples affect grouping |
| Pit Window | Signed observed time swing; positive favours the early stopper | Nearby rivals with complete green timing windows and stops one to three laps apart | Pit-lane duration includes entry/exit; residual is not isolated mechanic or strategy performance |
| Pit Timing | Retrospective seconds relative to nearby stop-lap scenarios | Complete supported clean-air/reference windows; interior versus boundary minimum shown separately | The fitted pace component underperforms a constant baseline; boundary minima do not locate an optimum |
| Race Control | Separate position, gap, pit, tyre and recovery observations/estimates | Each component has its own eligibility, unit, reference count and source class | Components overlap and must not be added into a total causal race-result effect |
| Racecraft / Replay passes | Experimental resolved battle or pass detections | Continuity and event rules; rate denominators and Wilson intervals shown | Timing-source agreement is not independent footage validation or population accuracy |
| Weather / Speed | Compound/weather lap summaries and observed speed samples | Weather aligned within lap windows; aggregate weather comparison needs five races | Association is not weather causality; speed and weather have separate source scope |

</div>

Exact filters and excluded observations are available on each analysis page.
The cockpit brings those results together; it does not create a new causal score.

## Uncertainty and missing data

- **Resampling interval:** variability under the stated sampling/model procedure.
  It does not include every source error or model misspecification. Individual
  intervals cannot be subtracted to obtain a paired interval or win probability.
- **P25/P75:** the middle half of observed values, not a confidence interval.
- **Heuristic evidence grade:** a rule based on coverage and sample counts, not
  a calibrated probability of correctness.
- **Missing / excluded:** no supported estimate. This is different from an
  observed zero. Source ingestion with no returned rows does not establish that
  no pit visit, radio message or other real-world event occurred.
- **Censored bound:** only a limit is observed, such as settling beyond six laps.
  It must not be ranked as an exact duration.

## Validation status

These analyses are exploratory, not certified.

### Latest documented review: 14 September 2026

**Independent footage review: 0 of 3 prepared windows scored.** Both reviewer
templates remain pending. No precision, recall or population accuracy estimate
is available from that review. This describes the committed review batch, not
a live count of independently verified events in the selected snapshot.

Frozen OpenF1 comparisons provide additional source evidence. In the selected
Austria 2025 NOR/PIA window, the source streams contain two order exchanges
absent from the reconstructed replay. In Monza, two detected exchanges agree
in direction but occur about 15.7 and 18.8 seconds later than the aligned feed.
The selected Spa window contains no source pair exchange; this does not prove
that exhaustive footage review would find none. These feeds may share upstream
timing provenance and are not independent physical ground truth.

The 14 September detector audit removed one event without the required
post-swap observations and 47 events whose completion times overlapped observed
pit intervals. Removing these unsupported confirmations does not certify the
remaining events or establish that no physical pass occurred at another time.
Within-lap exchanges, timing errors and incomplete pit observations remain open.

[Review protocol and pending annotations](https://github.com/denzlswaggin/f1-data-analytics/blob/main/docs/racecraft-reference-review.md)
· [Frozen source comparisons](https://github.com/denzlswaggin/f1-data-analytics/blob/main/docs/racecraft-openf1-comparison.md)
· [Persistence audit](https://github.com/denzlswaggin/f1-data-analytics/blob/main/docs/overtake-persistence.md)
· [Pit-interval audit](https://github.com/denzlswaggin/f1-data-analytics/blob/main/docs/overtake-pit-intervals.md)

### Latest completed fitting diagnostic: 18 September 2026

On `20260918-audit-core-pages`, the production robust fitting kernel used in
pit timing was fitted on the first eight eligible clean-air laps of each stint
and evaluated on later laps. Across 871 stints and 9,041 later laps, mean absolute
error was **1.136 s**, compared with **0.652 s** for the training-median constant.
The fitted trend was worse than that baseline.

This evaluates a fitting component under the diagnostic's selection rules, not
the complete production strategy model. It uses already inspected races and
derived pace targets; it provides no calibrated uncertainty or counterfactual
strategy accuracy. [Protocol and complete reports](https://github.com/denzlswaggin/f1-data-analytics/blob/main/docs/production-kernel-temporal-diagnostic.md).

### Historical reference panel: 11 September snapshot

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

### Historical pit and race-control source checks

On the same snapshot, 12 selected pit-stop windows in Bahrain and Imola 2025
cover 600 driver-laps. All 25 officially listed stops match exactly, with no
extra pit-entry detections in those windows. Four positive SC/VSC/red-flag
probes also match the reported lap.

These checks use official sources that may share timing provenance with the
app's inputs: they verify source agreement, **not independent sensor accuracy**.
Pit-table and narrative-report lap conventions can differ. They do not establish
global precision, accurate race-control effects or calibrated uncertainty.
[Read the window protocol and remaining limitations](https://github.com/denzlswaggin/f1-data-analytics/blob/main/docs/event-window-validation.md).

### Historical pass-sequence review

Three provisional pair windows checked event direction and order, with replay
coverage required for both drivers. Monza's lap 2 position return and lap 4 pass
match in order; no pass is detected in the selected Spa Leclerc/Verstappen window.

In Austria's lap 11, neither short lead exchange described by the race report
appears in the detector output. The reconstructed replay keeps Norris first
throughout that lap. The source descriptions and minimum pass duration still
need footage review to adjudicate physical events. The later source comparisons
above establish a feed-to-model discrepancy but do not complete that review.
These provisional labels do not support a precision or accuracy score.
[Read the sequence protocol and finding](https://github.com/denzlswaggin/f1-data-analytics/blob/main/docs/pass-window-validation.md).

## What the rating means

The model compares teammates in the last qualifying segment both completed,
turns their time ratio into an additive log-pace gap, and solves the connected
teammate graph with regularisation. This reduces the largest shared car effect;
it does not remove upgrade timing, setup, traffic, reliability, injury, or every
change in teammate strength.

The career model answers “who was consistently fast relative to teammates?”.
The dynamic model answers “how did that relative form change by season?”. Its
90% intervals resample complete race weekends within seasons. Static career
intervals instead resample undirected teammate comparison edges: mirrored rows
stay together, but different teams at one weekend are not clustered together.
These are individual estimate intervals, not exact-rank probabilities.

## Published data contract

<DataTable data={snapshot} rows=1>
    <Column id=version />
    <Column id=generated_at title="Published at" />
    <Column id=source title="Warehouse" />
    <Column id=latest_event_date title="Latest event" />
</DataTable>

```sql coverage
select section, season, round, race_label, sample_rows, sample_unit, entity_count, race_count, usable_samples, usable_unit, coverage_reason,
       first_season, last_season, latest_event_date
from f1.data_coverage
order by section, race_label desc
```

<div style="overflow-x: auto; max-width: 100%;">
<DataTable data={coverage} rows=50 download=true />
</div>

Every deployment consumes an immutable DuckDB snapshot. Its SHA-256 is checked
before the site builds, and the data contract blocks publication when required
ratings, strategy, telemetry, or replay partitions are missing. Coverage differs
by source because FastF1 telemetry is substantially heavier than Jolpica results.

For equations, validation and known limitations, see the
[model documentation](https://github.com/denzlswaggin/f1-data-analytics/blob/main/docs/dynamic-rating-model.md).

<RelatedAnalysis section="trust" current="methodology" />
