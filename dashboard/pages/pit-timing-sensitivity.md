---
title: Pit Timing Sensitivity
hide_title: true
max_width: 1600
---

<AppNav />

<PageHeader
    eyebrow="Strategy intelligence"
    title="How sensitive was the stop to its timing?"
    description="Replay each observed dry-tyre stop from three laps earlier to three laps later, using the driver's clean-air pace before and after the stop."
    accent="strategy"
/>

<KeyInsight label="A sensitivity test, not a strategy oracle">
The model moves the same observed stop and tyre-set transition. It does not know the traffic, pit loss, tyre inventory or race-control state that would have occurred in the alternate future. A supported shift is evidence that timing mattered in the observed pace window—not proof that the team should have made that call.
</KeyInsight>

<KeyInsight label="Temporal diagnostic: the fitted trend did not beat a constant baseline">
On snapshot 20260918-audit-core-pages, 871 stints had enough evidence for the
first-eight-laps training protocol. Holdout MAE was **1.136 s** for the production
Theil-Sen fitting kernel versus **0.652 s** for the training-median baseline
(lower is better). This is a retrospective component diagnostic, not validation
of the complete counterfactual strategy model. Treat scenario gains as exploratory.
</KeyInsight>

```sql seasons
select distinct season
from f1.pit_timing_races
where season between 2024 and 2026
order by season desc
```

```sql races
select distinct
    season,
    round,
    race_name,
    'R' || lpad(cast(round as varchar), 2, '0') || ' · '
        || replace(race_name, ' Grand Prix', '')
        || ' · ' || cast(eligible_stops as integer) || '/' || cast(observed_stops as integer)
        || ' supported stops' as race_label
from f1.pit_timing_races
where season = ${inputs.season.value}
order by round
```

<FilterBar title="Choose a race" description="Races are ordered by championship round; excluded stops remain visible with their evidence gap.">
    <QueryDropdown data={seasons} name=season value=season title="Season" />
    <DependentDropdown data={races} name=race value=round label=race_label order="round asc" title="Race" season={inputs.season.value} latest={true} preserveInitial={true} />
</FilterBar>

```sql coverage
select *, observed_stops as sample_rows, eligible_stops as usable_samples,
    'stops' as sample_unit, 'stops' as usable_unit, drivers as entity_count,
    1 as race_count, season as first_season, season as last_season,
    race_date as latest_event_date
from f1.pit_timing_races
where season = ${inputs.season.value} and round = ${inputs.race.value}
```

<DataTrust data={coverage} sampleLabel="observed stops" entityLabel="Drivers" method="clean-air ±3-lap counterfactual with bootstrap uncertainty" />

```sql season_coverage
select round, race_name, observed_stops, eligible_stops,
    observed_stops - eligible_stops as excluded_stops,
    case
        when lap_rows = 0 then 'Lap data unavailable'
        when replay_rows = 0 then 'Replay unavailable'
        when observed_stops = 0 then 'No analysed transitions'
        when eligible_stops = 0 then 'No stops pass the model rules'
        else 'Supported results available'
    end as evidence_status
from f1.pit_timing_races
where season = ${inputs.season.value}
order by round
```

<ExpandableSection title="Find races with supported results — season coverage" open=true>
All completed races with loaded results are listed. Input availability is separate
from model eligibility: a loaded replay does not guarantee enough clean reference
laps for a stop. Counts refer to observed tyre-stint transitions analysed by this model.

<DataTable data={season_coverage} rows=24 search=true>
    <Column id=round title="Round" fmt="0" />
    <Column id=race_name title="Race" />
    <Column id=observed_stops title="Observed stops" />
    <Column id=eligible_stops title="Supported stops" />
    <Column id=excluded_stops title="Excluded stops" />
    <Column id=evidence_status title="Evidence status" />
</DataTable>
</ExpandableSection>

```sql race_stops
select
    *,
    driver_code || ' · Stop ' || cast(cast(stop_number as integer) as varchar) as stop_label,
    old_compound || ' → ' || new_compound as compound_change,
    case
        when not eligible then 'Excluded'
        when boundary_minimum then 'Range-edge minimum; no optimum established'
        else timing_signal
    end as displayed_signal
from f1.pit_timing_sensitivity
where season = ${inputs.season.value} and round = ${inputs.race.value}
order by actual_pit_lap, driver_code, stop_number
```

```sql supported_stops
select * from ${race_stops} where eligible
```

```sql largest_supported_gain
select
    coalesce(arg_max(stop_label, estimated_gain_vs_actual_sec)
        filter (where not boundary_minimum and timing_signal <> 'No meaningful directional signal'),
        'No interior estimate') as stop_label,
    max(estimated_gain_vs_actual_sec)
        filter (where not boundary_minimum and timing_signal <> 'No meaningful directional signal') as estimated_gain_vs_actual_sec
from ${supported_stops}
```

```sql evidence_summary
select
    count(*) as observed_stops,
    count(*) filter (where eligible) as eligible_stops,
    count(*) filter (where timing_signal = 'No meaningful directional signal') as no_signal,
    count(*) filter (where eligible and boundary_minimum) as boundary_stops
from ${race_stops}
```

<Grid cols=4>
    <BigValue data={evidence_summary} value=boundary_stops title="Eligible minima at tested boundary" />
    <BigValue data={largest_supported_gain} value=stop_label comparison=estimated_gain_vs_actual_sec comparisonFmt="0.00 s modelled gain" title="Largest interior timing signal" />
    <BigValue data={evidence_summary} value=eligible_stops comparison=observed_stops comparisonFmt="0 observed stops" title="Eligible stops" />
    <BigValue data={evidence_summary} value=no_signal title="No meaningful directional signal" />
</Grid>

{#if coverage[0]?.observed_stops === 0}
<KeyInsight label="No analysed stops">
This completed race has no analysed tyre-stint transitions in the loaded data.
That does not establish that no pit stops occurred.
</KeyInsight>
{:else if evidence_summary[0]?.eligible_stops === 0}
<KeyInsight label="No supported timing estimate">
The observed stops are available below, but none passes every model rule.
Select any stop to inspect its recorded context and exclusion reason.
</KeyInsight>
{/if}

```sql exclusion_summary
select replace(exclusion_reason, '_', ' ') as reason, count(*) as stops
from ${race_stops}
where not eligible
group by exclusion_reason
order by stops desc, reason
```

<ExpandableSection title="Why stops are excluded">
Each stop is counted once, under the first failed rule. Later checks may not have
run; blank diagnostics and zero reference counts do not prove the underlying feed
is missing. Incomplete windows can also come from retirement or the end of a race.
<DataTable data={exclusion_summary} rows=15>
    <Column id=reason title="First failed rule" />
    <Column id=stops title="Stops" />
</DataTable>
</ExpandableSection>

## Stop timing overview — {inputs.season.value} {inputs.race.label}

The displayed shift is the lowest modelled cost among the supported scenarios. A
negative shift means stopping earlier; a positive shift means stopping later.
The directional finding requires at least 0.30 seconds of estimated gain and a
75th percentile resampling delta below zero before calling a direction supported.
Otherwise the result has no meaningful directional signal; this can reflect
the practical gain threshold, not necessarily a spread that contains zero.
An edge minimum gives a direction within the tested range, not an optimal pit
lap. Rejected scenarios remain visible below with their extrapolation distances.

<DataTable data={race_stops} rows=40 search=true download=true>
    <Column id=driver_code title="Driver" />
    <Column id=stop_number title="Stop" />
    <Column id=actual_pit_lap title="Actual pit lap" />
    <Column id=compound_change title="Tyres" />
    <Column id=best_supported_shift_laps title="Lowest-cost tested shift (laps)" fmt="+0;-0;0" />
    <Column id=estimated_gain_vs_actual_sec title="Modelled gain (s)" fmt="0.000" />
    <Column id=best_delta_p25_sec title="Δ P25 (s)" fmt="+0.000;-0.000" />
    <Column id=best_delta_p75_sec title="Δ P75 (s)" fmt="+0.000;-0.000" />
    <Column id=best_shift_win_pct title="Fractional bootstrap wins (%)" fmt="0.0" />
    <Column id=boundary_minimum title="Range-edge minimum" />
    <Column id=displayed_signal title="Finding" />
    <Column id=confidence title="Heuristic evidence" />
</DataTable>

```sql stop_choices
select season, round, stop_label,
    stop_label || case when eligible then ' · Supported' else ' · Excluded' end as choice_label
from ${race_stops}
order by actual_pit_lap, driver_code, stop_number
```

<FilterBar title="Inspect one stop" description="All observed stops are selectable. Supported curves compare timing within the same 13-lap evaluation window.">
    <DependentDropdown data={stop_choices} name=stop value=stop_label label=choice_label title="Driver and stop" season={inputs.season.value} round={inputs.race.value} />
</FilterBar>

```sql selected_stop
select * from ${race_stops}
where stop_label = '${inputs.stop.value}'
    and season = ${inputs.season.value} and round = ${inputs.race.value}
```

```sql selected_scenarios
select
    scenarios.*,
    case
        when shift_laps < 0 then 'Earlier'
        when shift_laps > 0 then 'Later'
        else 'Actual'
    end as timing_direction,
    case
        when shift_laps = 0 then 'Actual'
        when shift_laps > 0 then '+' || cast(shift_laps as varchar) || ' laps'
        else cast(shift_laps as varchar) || ' laps'
    end as shift_label
from f1.pit_timing_scenarios as scenarios
where season = ${inputs.season.value}
    and round = ${inputs.race.value}
    and driver_code || ' · Stop ' || cast(cast(stop_number as integer) as varchar) = '${inputs.stop.value}'
order by shift_laps
```

```sql supported_curve
select * from ${selected_scenarios} where supported
```

{#if selected_stop.length > 0}

## Stop evidence — {inputs.stop.value}

<DataTable data={selected_stop} rows=1>
    <Column id=actual_pit_lap title="Observed pit lap" />
    <Column id=compound_change title="Tyres" />
    <Column id=pit_duration_sec title="Recorded pit duration (s)" fmt="0.000" />
    <Column id=official_pit_match title="Official stop matched" />
    <Column id=window_start_lap title="Window start" />
    <Column id=window_end_lap title="Window end" />
</DataTable>

{#if selected_stop[0]?.eligible}

## Scenario curve — {inputs.stop.value}

Negative Δ is faster than the observed stop timing; positive Δ is slower. The
pit/out-lap transition is held constant in every scenario, so this chart isolates
the timing trade-off between extending the old stint and starting the new one.

<BarChart
    data={supported_curve}
    x=shift_label
    y=delta_vs_actual_sec
    series=timing_direction
    yAxisTitle="modelled Δ versus actual timing (s) — lower is better"
    labels=true
    sort=false
    chartAreaHeight=390
>
    <ReferenceLine y=0 label="actual timing" />
</BarChart>

{:else}

<KeyInsight label="Timing estimate excluded">
First failed rule: <strong>{selected_stop[0]?.exclusion_reason?.replaceAll('_', ' ')}</strong>.
The observed stop context remains available. No modelled gain is published for
this stop; uncomputed diagnostics are not evidence of a missing data feed.
</KeyInsight>

{/if}

<DataTable data={selected_scenarios} rows=7>
    <Column id=shift_laps title="Shift (laps)" fmt="+0;-0;0" />
    <Column id=hypothetical_pit_lap title="Pit lap" />
    <Column id=delta_vs_actual_sec title="Δ vs actual (s)" fmt="+0.000;-0.000" />
    <Column id=delta_p25_sec title="Bootstrap P25 (s)" fmt="+0.000;-0.000" />
    <Column id=delta_p75_sec title="Bootstrap P75 (s)" fmt="+0.000;-0.000" />
    <Column id=old_tyre_extension_laps title="Old-tyre extension" />
    <Column id=old_extrapolation_laps title="Old reference extrapolation (laps)" />
    <Column id=new_extrapolation_laps title="New reference extrapolation (laps)" />
    <Column id=supported title="Supported" />
    <Column id=exclusion_reason title="Exclusion reason" />
</DataTable>

```sql selected_evidence
select
    old_reference_laps,
    new_mature_reference_laps,
    warmup_profile_laps,
    old_slope_sec_per_tyre_lap,
    new_slope_sec_per_stint_lap,
    old_model_mad_sec,
    new_model_mad_sec,
    replay_coverage_pct,
    field_peer_count_median,
    bootstrap_requested_samples,
    bootstrap_valid_samples,
    bootstrap_attempted_samples,
    actual_old_extrapolation_laps,
    actual_new_extrapolation_laps,
    best_old_extrapolation_laps,
    best_new_extrapolation_laps,
    pit_duration_sec,
    official_pit_match
from ${selected_stop}
```

<DataTable data={selected_evidence} rows=1>
    <Column id=old_reference_laps title="Old-stint refs" />
    <Column id=new_mature_reference_laps title="New mature refs" />
    <Column id=warmup_profile_laps title="Settling refs" />
    <Column id=old_slope_sec_per_tyre_lap title="Old trend (s/lap)" fmt="+0.000;-0.000" />
    <Column id=new_slope_sec_per_stint_lap title="New trend (s/lap)" fmt="+0.000;-0.000" />
    <Column id=old_model_mad_sec title="Old fit MAD (s)" fmt="0.000" />
    <Column id=new_model_mad_sec title="New fit MAD (s)" fmt="0.000" />
    <Column id=replay_coverage_pct title="Replay coverage (%)" fmt="0.0" />
    <Column id=field_peer_count_median title="Median field peers" fmt="0.0" />
    <Column id=bootstrap_requested_samples title="Requested draws" />
    <Column id=bootstrap_valid_samples title="Valid draws" />
    <Column id=bootstrap_attempted_samples title="Attempted draws" />
    <Column id=actual_old_extrapolation_laps title="Actual old extrapolation" />
    <Column id=actual_new_extrapolation_laps title="Actual new extrapolation" />
    <Column id=best_old_extrapolation_laps title="Selected old extrapolation" />
    <Column id=best_new_extrapolation_laps title="Selected new extrapolation" />
</DataTable>

{/if}

```sql excluded_stops
select stop_label, actual_pit_lap, compound_change, exclusion_reason,
    bootstrap_requested_samples, bootstrap_valid_samples, bootstrap_attempted_samples,
    actual_old_extrapolation_laps, actual_new_extrapolation_laps
from ${race_stops}
where not eligible
```

<ExpandableSection title="See excluded stops and the v3 method">
<DataTable data={excluded_stops} rows=40 search=true />

A stop needs a complete green-flag window from three laps before its out-lap to
nine laps after it, no second stop in that window, a dry supported compound
transition, four to six clean old-stint reference laps, all six post-stop
settling offsets and at least three mature new-stint references. Each reference
lap needs at least 80% replay coverage and five other clean-air field peers.

The old and new trends use robust Theil–Sen fits. The early settling profile
moves with the hypothetical stop rather than remaining attached to its original
race laps. Deterministic resampling reports P25/P75 uncertainty and how often the
point-estimate minimum wins the bootstrap samples, with equal fractional credit
for tied minima. Pit duration is displayed
as context but is not added to the scenario delta because the same stop occurs
in every scenario. Results do not model alternate traffic or race events.

The extrapolation policy permits at most four old-tyre laps and three mature
new-tyre laps outside their respective observed reference ranges. These are
operational limits, not validated physical thresholds. The actual baseline must
pass both limits before any comparison; alternatives are gated individually.
The six observed settling offsets are reused exactly and do not count as mature
model extrapolation. A range-edge minimum, including an edge created by rejected
scenarios, establishes no optimum outside the supported window.

Independent-row resampling is conditional on the selected clean-air laps and
field peers; warmup observations and the model family remain fixed. P25/P75 is
the middle 50% resampling spread, not a confidence interval with guaranteed
coverage. At least 100 valid draws and 90% of the requested draws are required
before publishing estimates. Non-finite fits are rejected. The evidence label
and publication cutoffs are operational safeguards, not validated calibration.
The evidence label
is heuristic, not a calibrated probability; range-edge minima and fewer than
300 valid draws cannot receive high evidence. Serial dependence, alternate
traffic and field-reference uncertainty are not captured by this bootstrap.
</ExpandableSection>

<RelatedAnalysis section="race" current="pit-timing-sensitivity" season={inputs.season.value} race={inputs.race.value} />
