---
title: Who Was Fast in Clean Air?
hide_title: true
max_width: 1600
---

<AppNav />

<PageHeader
    eyebrow="Race analysis"
    title="Who was fast in clean air?"
    description="Separate representative clean-air laps from traffic-exposed running, with replay coverage and metric-specific heuristic sample strength."
/>

<KeyInsight label="How to read this">
Lower clean-air controlled pace is faster. A positive traffic-associated delta means the driver's matched traffic laps were slower, but it is an observed association—not proof that dirty air caused the difference.
</KeyInsight>

```sql seasons
select distinct season
from f1.traffic_adjusted_pace
where season > 0
order by season desc
```

```sql races
select distinct
    season,
    round,
    race_name,
    'R' || lpad(cast(round as varchar), 2, '0') || ' · '
        || replace(race_name, ' Grand Prix', '') as race_label
from f1.traffic_adjusted_pace
where season = ${inputs.season.value}
order by round
```

<FilterBar title="Choose a race" description="Only races with both green-flag lap timing and replay gaps are available.">
    <QueryDropdown data={seasons} name=season value=season title="Season" />
    <DependentDropdown data={races} name=race value=round label=race_label order="round asc" title="Race" season={inputs.season.value} latest={true} preserveInitial={true} />
</FilterBar>

```sql coverage
select * from f1.data_coverage
where section = 'traffic_pace'
    and season = cast(${inputs.season.value} as integer)
    and round = cast(${inputs.race.value} as integer)
```

<DataTrust data={coverage} sampleLabel="eligible laps" entityLabel="Drivers" method="descriptive clean-air matching" />

```sql race_results
select
    *,
    case when clean_air_eligible then
        rank() over (order by case when clean_air_eligible then traffic_adjusted_pace_delta_sec end nulls last)
    end as clean_air_rank
from f1.traffic_adjusted_pace
where season = ${inputs.season.value} and round = ${inputs.race.value}
order by traffic_adjusted_pace_delta_sec nulls last, driver_code
```

```sql clean_air_leader
select driver_code, traffic_adjusted_pace_delta_sec
from ${race_results}
where clean_air_eligible and traffic_adjusted_pace_delta_sec is not null
order by traffic_adjusted_pace_delta_sec
limit 1
```

```sql exposure_leader
select driver_code, traffic_exposure_pct
from ${race_results}
where traffic_exposure_pct is not null
order by traffic_exposure_pct desc nulls last
limit 1
```

```sql association_leader
select driver_code, traffic_associated_delta_sec_per_lap
from ${race_results}
where traffic_association_eligible and traffic_associated_delta_sec_per_lap is not null
order by traffic_associated_delta_sec_per_lap desc
limit 1
```

<Grid cols=3>
    {#if clean_air_leader.length > 0}
<BigValue data={clean_air_leader} value=driver_code title="Fastest clean-air pace" />
{:else}
<KeyInsight label="Fastest clean-air pace">Insufficient eligible evidence.</KeyInsight>
{/if}
    {#if exposure_leader.length > 0}
<BigValue data={exposure_leader} value=driver_code title="Highest traffic exposure" />
{:else}
<KeyInsight label="Highest traffic exposure">Insufficient eligible evidence.</KeyInsight>
{/if}
    {#if association_leader.length > 0}
<BigValue data={association_leader} value=driver_code title="Largest traffic association" />
{:else}
<KeyInsight label="Largest traffic association">Insufficient eligible evidence.</KeyInsight>
{/if}
</Grid>

```sql metric_samples
select count(*) as candidate_drivers,
    count(*) filter (where clean_air_eligible) as clean_air_drivers,
    count(*) filter (where traffic_association_eligible) as association_drivers,
    coalesce(sum(clean_air_laps), 0) as clean_laps,
    coalesce(sum(matched_traffic_laps), 0) as matched_laps
from ${race_results}
```

<DataTable data={metric_samples}>
    <Column id=candidate_drivers title="Candidate drivers" />
    <Column id=clean_air_drivers title="Clean-air eligible" />
    <Column id=association_drivers title="Association eligible" />
    <Column id=clean_laps title="Clean laps" />
    <Column id=matched_laps title="Matched traffic laps" />
</DataTable>

Clean-air and association eligibility differ. A blank association is missing
evidence, not a measured zero effect. Lap counts are observations within drivers,
not independent race replications. Rankings use point estimates, without evidence
that adjacent drivers are statistically distinguishable.

## Clean-air pace ranking — {inputs.season.value} {inputs.race.label}

Each lap is compared with the leave-one-driver-out median of at least three
other drivers on the same lap and compound. The ranking is the median of those
deltas on clean-air laps. A driver needs five clean laps before publication.
The three-peer cutoff is a conservative heuristic, not an externally validated
precision threshold. A median reduces one extreme peer's influence but cannot
remove shared biases, car differences or unmeasured race context.

```sql clean_air_results
select * from ${race_results}
where clean_air_eligible and traffic_adjusted_pace_delta_sec is not null
```

{#if clean_air_results.length > 0}
<BarChart
    data={clean_air_results}
    x=driver_code
    y=traffic_adjusted_pace_delta_sec
    yAxisTitle="clean-air controlled pace delta (s) — lower is faster"
    labels=true
>
    <ReferenceLine y=0 label="peer median" />
</BarChart>
{:else}
<KeyInsight label="Insufficient evidence">No eligible observations support this chart for the current selection. See the evidence and exclusions below.</KeyInsight>
{/if}

## Traffic exposure versus associated pace

Exposure is tick-weighted across all eligible laps. The vertical measure pairs
each traffic lap with clean laps from the same driver and compound within two
laps of tyre age. P25 and P75 describe the middle half of the observed matched
lap differences, not a confidence interval. Heuristic sample strength describes
the available counts, not a calibrated probability or the accuracy of the estimate.

```sql association
select *
from ${race_results}
where traffic_association_eligible and traffic_associated_delta_sec_per_lap is not null
```

{#if association.length > 0}
<ScatterPlot
    data={association}
    x=traffic_exposure_pct
    y=traffic_associated_delta_sec_per_lap
    series=driver_code
    xAxisTitle="traffic exposure (% of valid replay ticks)"
    yAxisTitle="traffic-associated delta (s/lap)"
    chartAreaHeight=380
>
    <ReferenceLine y=0 label="no observed association" />
</ScatterPlot>
{:else}
<KeyInsight label="Insufficient evidence">No eligible observations support this chart for the current selection. See the evidence and exclusions below.</KeyInsight>
{/if}

<div style="overflow-x: auto; max-width: 100%;">
<DataTable data={race_results} rows=25 search=true download=true>
    <Column id=clean_air_rank title="Rank" />
    <Column id=driver_code title="Driver" />
    <Column id=team title="Team" />
    <Column id=traffic_adjusted_pace_delta_sec title="Clean-air pace (s)" fmt="+0.000;-0.000" />
    <Column id=traffic_exposure_pct title="Traffic (%)" fmt="0.0" />
    <Column id=traffic_associated_delta_sec_per_lap title="Associated Δ (s/lap)" fmt="+0.000;-0.000" />
    <Column id=traffic_associated_p25_sec title="P25 (s)" fmt="+0.000;-0.000" />
    <Column id=traffic_associated_p75_sec title="P75 (s)" fmt="+0.000;-0.000" />
    <Column id=clean_air_laps title="Clean laps" />
    <Column id=matched_traffic_laps title="Matched traffic laps" />
    <Column id=replay_coverage_pct title="Replay coverage (%)" fmt="0.0" />
    <Column id=clean_air_eligible title="Clean-air eligible" />
    <Column id=clean_air_confidence title="Clean-air sample strength" />
    <Column id=traffic_association_eligible title="Association eligible" />
    <Column id=traffic_association_confidence title="Association sample strength" />
</DataTable>
</div>

```sql drivers
select distinct season, round, driver_code
from f1.traffic_adjusted_laps
where season = ${inputs.season.value} and round = ${inputs.race.value}
order by driver_code
```

<FilterBar title="Inspect the lap evidence" description="Mixed laps remain visible but never enter the clean-air headline.">
    <DependentDropdown data={drivers} name=driver value=driver_code title="Driver" season={inputs.season.value} round={inputs.race.value} />
</FilterBar>

```sql lap_evidence
select
    lap_number,
    air_state,
    compound,
    tyre_life,
    median_gap_to_ahead_s,
    replay_coverage_pct,
    peer_count,
    peer_lap_median_sec,
    peer_lap_avg_sec,
    controlled_pace_delta_sec,
    paired_traffic_delta_sec
from f1.traffic_adjusted_laps
where season = ${inputs.season.value}
    and round = ${inputs.race.value}
    and driver_code = '${inputs.driver.value}'
order by lap_number
```

{#if lap_evidence.length > 0}
<LineChart
    data={lap_evidence}
    x=lap_number
    y=controlled_pace_delta_sec
    series=air_state
    yAxisTitle="controlled pace delta (s)"
    chartAreaHeight=340
>
    <ReferenceLine y=0 label="peer median" />
</LineChart>
{:else}
<KeyInsight label="Insufficient evidence">No eligible observations support this chart for the current selection. See the evidence and exclusions below.</KeyInsight>
{/if}

<ExpandableSection title="See every included lap and the method">
<div style="overflow-x: auto; max-width: 100%;">
<DataTable data={lap_evidence} rows=80 download=true />
</div>

Traffic is at least 50% of valid replay ticks within 1.5 seconds of a car ahead.
Clean air is at least 80% leading or three seconds clear, with no more than 10%
close traffic. Classification needs 80% coverage by usable order/gap observations,
not just replay rows. Missing or invalid values cannot establish clear air.
Lap one, pit in/out laps, unknown
compounds and tyre life below two are excluded. Gaps are reconstructed from lap
timing and do not capture every lapped-car interaction, so this analysis must not
be read as a causal counterfactual finish result.

Method: `traffic-v4-robust-peers`. Lap evidence shows the number of other drivers
and their median baseline. The arithmetic peer average remains a diagnostic only;
it is not the baseline used for controlled deltas. Each driver contributes at
most one lap observation to a peer group, and their own time is excluded.

Clean-air pace requires at least five clean
laps; the traffic association requires both five clean laps and five matched
traffic laps. A clean-air estimate can therefore be eligible even when the
association is unavailable. Clean-air sample strength uses the clean-lap count;
association sample strength uses the smaller of clean and matched-traffic counts.
For each metric, five to seven samples are low, eight to eleven medium and twelve
or more high; below five is insufficient. These are heuristic sample-strength
labels, not statistical confidence levels. The exported legacy `confidence`
field remains an alias for traffic-association sample strength only.
</ExpandableSection>

```sql excluded_pit_laps
select driver_code, lap_number, pit_context_source, pit_exclusion_reason
from f1.pit_lap_context
where season = ${inputs.season.value} and round = ${inputs.race.value}
    and is_pit_boundary
order by driver_code, lap_number
```

<ExpandableSection title="Pit laps excluded from pace references">
Pit visits are excluded even when the tyre stint does not change. Evidence
combines available pit-entry/exit timestamps, recorded pit laps and inferred
stint boundaries. Missing pit records do not prove that no pit visit occurred.

<div style="overflow-x: auto; max-width: 100%;">
<DataTable data={excluded_pit_laps} rows=40 search=true download=true>
    <Column id=driver_code title="Driver" />
    <Column id=lap_number title="Lap" />
    <Column id=pit_context_source title="Evidence source" />
    <Column id=pit_exclusion_reason title="Exclusion" />
</DataTable>
</div>
</ExpandableSection>

<RelatedAnalysis section="race" current="traffic-adjusted-pace" season={inputs.season.value} race={inputs.race.value} />
