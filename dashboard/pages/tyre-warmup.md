---
title: How Quickly Did Pace Settle?
max_width: 1600
---

<AppNav />

<PageHeader
    eyebrow="Tyre analysis"
    title="How quickly did pace settle?"
    description="Track the clean-air pace transition after a stop, separating early-stint settling from the mature degradation trend."
    accent="strategy"
/>

<KeyInsight label="What this measures">
A positive settling loss means a lap was slower than the pace expected from that stint's later mature trend. Stable pace is confirmed only after two consecutive clean-air laps within ±0.50 s. This is timing evidence—not tyre-temperature telemetry or a causal compound comparison.
</KeyInsight>

```sql seasons
select distinct season
from f1.tyre_warmup
where season > 0
order by season desc
```

```sql races
select distinct
    round,
    race_name,
    'R' || lpad(cast(round as varchar), 2, '0') || ' · '
        || replace(race_name, ' Grand Prix', '') as race_label
from f1.tyre_warmup
where season = ${inputs.season.value}
order by round
```

<FilterBar title="Choose a race" description="Available races have lap timing plus sufficient replay-derived traffic context.">
    <Dropdown data={seasons} name=season value=season title="Season" />
    <Dropdown data={races} name=race value=round label=race_label order="round asc" title="Race" />
</FilterBar>

```sql coverage
select * from f1.data_coverage
where section = 'tyre_warmup'
    and race_label = (
        select cast(season as varchar) || ' ' || race_name
        from f1.tyre_warmup
        where season = ${inputs.season.value} and round = ${inputs.race.value}
        limit 1
    )
```

<DataTrust data={coverage} sampleLabel="candidate stints" entityLabel="Drivers" method="clean-air mature-trend extrapolation" />

```sql race_stints
select
    *,
    driver_code || ' · S' || cast(stint as varchar) as driver_stint,
    case
        when stable_pace_achieved then 'Stable pace reached'
        when right_censored then 'Beyond 6 clean laps'
        when warmup_eligible then 'Incomplete observation'
        else 'Excluded'
    end as settling_status
from f1.tyre_warmup
where season = ${inputs.season.value} and round = ${inputs.race.value}
order by out_lap, driver_code
```

```sql fastest_settling
select driver_stint, time_to_pace_laps
from ${race_stints}
where stable_pace_achieved
order by time_to_pace_laps, first_flying_warmup_loss_sec
limit 1
```

```sql largest_first_lap_loss
select driver_stint, first_flying_warmup_loss_sec
from ${race_stints}
where warmup_eligible and first_flying_warmup_loss_sec is not null
order by first_flying_warmup_loss_sec desc
limit 1
```

```sql outcome_counts
select
    count(*) filter (where stable_pace_achieved) as achieved,
    count(*) filter (where right_censored) as beyond_six,
    count(*) filter (where warmup_eligible and not crossover_eligible) as incomplete
from ${race_stints}
```

<Grid cols=3>
    <BigValue data={fastest_settling} value=driver_stint comparison=time_to_pace_laps comparisonFmt="0 laps" title="Earliest confirmed stable pace" />
    <BigValue data={largest_first_lap_loss} value=driver_stint comparison=first_flying_warmup_loss_sec comparisonFmt="+0.00;-0.00 s" title="Largest first-flying loss" />
    <BigValue data={outcome_counts} value=achieved comparison=beyond_six comparisonFmt="0 beyond lap 6" title="Stable pace achieved" />
</Grid>

## Settling curve — {inputs.season.value} {inputs.race.label}

The first six full laps are compared with a robust Theil–Sen mature trend fitted
only on clean-air laps 7–12. Lower is better; zero follows the expected mature
trajectory and the shaded interpretation band is ±0.50 seconds.

```sql compound_curve
select
    compound,
    post_stop_offset,
    median(warmup_loss_sec) as median_settling_loss_sec,
    count(*) as samples
from f1.tyre_warmup_laps
where season = ${inputs.season.value}
    and round = ${inputs.race.value}
    and lap_eligible
    and post_stop_offset between 1 and 6
group by compound, post_stop_offset
order by post_stop_offset, compound
```

<LineChart
    data={compound_curve}
    x=post_stop_offset
    y=median_settling_loss_sec
    series=compound
    xAxisTitle="full laps after out-lap"
    yAxisTitle="median loss versus mature trend (s)"
    chartAreaHeight=390
>
    <ReferenceLine y=0 label="mature trajectory" />
    <ReferenceLine y=0.5 label="stable-band ceiling" />
    <ReferenceLine y=-0.5 label="stable-band floor" />
</LineChart>

## Which stints took longest?

Time-to-pace counts the confirming lap, not the first lap that entered the band.
A point at four therefore means offsets three and four were both within ±0.50 s.

```sql completed_stints
select * from ${race_stints}
where stable_pace_achieved
order by time_to_pace_laps desc, first_flying_warmup_loss_sec desc
```

<ScatterPlot
    data={completed_stints}
    x=first_flying_warmup_loss_sec
    y=time_to_pace_laps
    series=compound
    xAxisTitle="first-flying loss versus mature trend (s)"
    yAxisTitle="laps to confirmed stable pace"
    tooltipTitle=driver_stint
    pointSize=26
/>

```sql ranked_losses
select * from ${race_stints}
where warmup_eligible and first_flying_warmup_loss_sec is not null
order by first_flying_warmup_loss_sec desc
limit 24
```

<BarChart
    data={ranked_losses}
    x=driver_stint
    y=first_flying_warmup_loss_sec
    series=compound
    yAxisTitle="first-flying loss versus mature trend (s)"
    labels=true
>
    <ReferenceLine y=0 label="mature trajectory" />
</BarChart>

## Stint evidence

<DataTable data={race_stints} rows=30 search=true download=true>
    <Column id=driver_code title="Driver" />
    <Column id=stint title="Stint" />
    <Column id=compound title="Compound" />
    <Column id=out_lap title="Out-lap" />
    <Column id=first_flying_warmup_loss_sec title="First flying Δ (s)" fmt="+0.000;-0.000" />
    <Column id=second_flying_warmup_loss_sec title="Second flying Δ (s)" fmt="+0.000;-0.000" />
    <Column id=first_two_lap_warmup_cost_sec title="Positive loss, first 2 (s)" fmt="0.000" />
    <Column id=time_to_pace_laps title="Laps to pace" />
    <Column id=settling_status title="Result" />
    <Column id=mature_reference_laps title="Mature samples" />
    <Column id=baseline_slope_sec_per_lap title="Mature slope (s/lap)" fmt="+0.000;-0.000" />
    <Column id=confidence title="Confidence" />
</DataTable>

```sql excluded_stints
select driver_stint, compound, out_lap, stint_laps, exclusion_reason
from ${race_stints}
where not warmup_eligible
```

<ExpandableSection title="See excluded stints and the v1 method">
<DataTable data={excluded_stints} rows=30 search=true />

The inferred out-lap (offset 0) is never timed because its lap time can include
stationary pit time. A candidate needs a contiguous stint change, at least 11
recorded laps, a dry compound, a clean first flying lap with at least 80% replay
coverage, and at least three clean mature-reference laps. The mature trend is
rejected when its absolute slope exceeds 0.50 s/lap or its median residual
exceeds 0.50 s. Used tyres remain eligible but cannot receive high confidence.

This analysis measures settling relative to later race pace. It cannot observe
tyre temperature or energy, and it does not claim that one compound causally
crosses over another. A missing result after traffic or a neutralisation is
reported as incomplete; only six fully observed clean laps can be right-censored.
</ExpandableSection>

<RelatedAnalysis section="race" current="tyre-warmup" season={inputs.season.value} race={inputs.race.value} />
