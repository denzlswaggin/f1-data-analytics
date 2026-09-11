---
title: Driver Pace Consistency
max_width: 1600
---

<AppNav />

<PageHeader
    eyebrow="Driver intelligence"
    title="Who repeated their pace most reliably?"
    description="Measure clean-air lap-to-lap consistency after removing each stint's underlying tyre-life trend, with the unexplained slow-lap tail kept visible."
    accent="drivers"
/>

<KeyInsight label="Repeatability, not a mistake counter">
Lower robust consistency is more repeatable. Slow-tail cost counts only the portion of an eligible lap above a transparent track-scaled threshold. Damage, management, blue flags, changing conditions and timing noise can still remain, so these observations are not labelled as driver errors.
</KeyInsight>

```sql seasons
select distinct season
from f1.pace_consistency
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
from f1.pace_consistency
where season = ${inputs.season.value}
order by round
```

<FilterBar title="Choose a race" description="Available races have sufficient lap timing and replay-derived clean-air context.">
    <Dropdown data={seasons} name=season value=season title="Season" />
    <DependentDropdown data={races} name=race value=round label=race_label order="round asc" title="Race" season={inputs.season.value} latest={true} preserveInitial={true} />
</FilterBar>

```sql coverage
select * from f1.data_coverage
where section = 'pace_consistency'
    and race_label = (
        select cast(season as varchar) || ' ' || race_name
        from f1.pace_consistency
        where season = ${inputs.season.value} and round = ${inputs.race.value}
        limit 1
    )
```

<DataTrust data={coverage} sampleLabel="candidate clean-air laps" entityLabel="Drivers" method="stint-level Theil–Sen trend; robust residual spread" />

```sql race_results
select
    *,
    case
        when consistency_eligible then rank() over (
            order by case when consistency_eligible then robust_consistency_sec end nulls last
        )
    end as consistency_rank
from f1.pace_consistency
where season = ${inputs.season.value} and round = ${inputs.race.value}
order by robust_consistency_sec nulls last, driver_code
```

```sql eligible_results
select * from ${race_results}
where consistency_eligible
```

```sql most_repeatable
select driver_code, robust_consistency_sec
from ${eligible_results}
where confidence in ('medium', 'high')
order by robust_consistency_sec, modelled_laps desc
limit 1
```

```sql largest_tail
select driver_code, slow_lap_cost_per_10_laps_sec
from ${eligible_results}
where confidence in ('medium', 'high')
order by slow_lap_cost_per_10_laps_sec desc, modelled_laps desc
limit 1
```

```sql evidence_count
select count(*) as drivers, sum(modelled_laps) as laps
from ${eligible_results}
```

<Grid cols=3>
    <BigValue data={most_repeatable} value=driver_code comparison=robust_consistency_sec comparisonFmt="0.000 s" title="Most repeatable pace" />
    <BigValue data={largest_tail} value=driver_code comparison=slow_lap_cost_per_10_laps_sec comparisonFmt="0.000 s / 10 laps" title="Largest observed slow tail" />
    <BigValue data={evidence_count} value=drivers comparison=laps comparisonFmt="0 modelled laps" title="Eligible drivers" />
</Grid>

Headline comparisons require medium or high heuristic evidence; low-evidence
estimates remain in the charts and table. No headline is shown if that subset is
empty. Point-estimate ranks do not establish statistically distinguishable drivers.
The underlying lap baseline is the median of at least three other cars on the
same lap and compound; small cohorts and correlated field effects remain limits.

## Consistency ranking — {inputs.season.value} {inputs.race.label}

The robust spread is 1.4826 × the median absolute deviation of model residuals.
Each stint has its own trend, so normal tyre degradation and different absolute
pace levels do not inflate the ranking. Lower is more repeatable.

<BarChart
    data={eligible_results}
    x=driver_code
    y=robust_consistency_sec
    series=confidence
    yAxisTitle="robust clean-air residual spread (s) — lower is better"
    labels=true
    sort=false
/>

## Repeatability versus the slow-lap tail

The horizontal axis measures ordinary lap-to-lap spread. The vertical axis is
the accumulated excess above the driver's threshold, normalised to ten eligible
laps so different sample sizes remain comparable.

<ScatterPlot
    data={eligible_results}
    x=robust_consistency_sec
    y=slow_lap_cost_per_10_laps_sec
    series=confidence
    tooltipTitle=driver_code
    xAxisTitle="robust consistency (s) — lower is better"
    yAxisTitle="unexplained slow-tail cost (s / 10 laps)"
    pointSize=28
    chartAreaHeight=390
/>

<DataTable data={race_results} rows=25 search=true download=true>
    <Column id=consistency_rank title="Rank" />
    <Column id=driver_code title="Driver" />
    <Column id=team title="Team" />
    <Column id=robust_consistency_sec title="Consistency (s)" fmt="0.000" />
    <Column id=robust_consistency_pct title="Consistency (% lap)" fmt="0.000" />
    <Column id=p90_slow_tail_sec title="P90 residual (s)" fmt="+0.000;-0.000" />
    <Column id=slow_lap_cost_per_10_laps_sec title="Slow-tail cost / 10 (s)" fmt="0.000" />
    <Column id=unexplained_slow_laps title="Slow-tail laps" />
    <Column id=modelled_laps title="Modelled laps" />
    <Column id=modelled_stints title="Stints" />
    <Column id=replay_coverage_pct title="Replay coverage (%)" fmt="0.0" />
    <Column id=confidence title="Evidence" />
</DataTable>

```sql drivers
select distinct season, round, driver_code
from f1.pace_consistency_laps
where season = ${inputs.season.value} and round = ${inputs.race.value}
    and lap_eligible
order by driver_code
```

<FilterBar title="Inspect one driver's evidence" description="Only clean-air laps from valid stint models enter the headline metrics.">
    <DependentDropdown data={drivers} name=driver value=driver_code title="Driver" season={inputs.season.value} round={inputs.race.value} />
</FilterBar>

```sql lap_evidence
select
    *,
    case
        when is_unexplained_slow_lap then 'Slow-tail excess'
        when lap_eligible then 'Within expected variation'
        else 'Excluded'
    end as lap_state
from f1.pace_consistency_laps
where season = ${inputs.season.value}
    and round = ${inputs.race.value}
    and driver_code = '${inputs.driver.value}'
order by lap_number
```

```sql modelled_laps
select * from ${lap_evidence} where lap_eligible
```

<BarChart
    data={modelled_laps}
    x=lap_number
    y=pace_residual_sec
    series=lap_state
    xAxisTitle="race lap"
    yAxisTitle="residual versus stint trend (s)"
    sort=false
    chartAreaHeight=360
>
    <ReferenceLine y=0 label="stint trend" />
</BarChart>

```sql stint_models
select
    stint,
    any_value(compound) as compound,
    max(stint_clean_laps) as clean_laps,
    max(stint_slope_sec_per_tyre_lap) as trend_sec_per_tyre_lap
from ${lap_evidence}
where lap_eligible
group by stint
order by stint
```

<DataTable data={stint_models} rows=10>
    <Column id=stint title="Stint" />
    <Column id=compound title="Compound" />
    <Column id=clean_laps title="Clean laps" />
    <Column id=trend_sec_per_tyre_lap title="Modelled trend (s/tyre lap)" fmt="+0.000;-0.000" />
</DataTable>

```sql excluded_laps
select lap_number, stint, compound, air_state, replay_coverage_pct, lap_exclusion_reason
from ${lap_evidence}
where not lap_eligible
```

<ExpandableSection title="See excluded laps and the robust-peer method">
<DataTable data={excluded_laps} rows=60 search=true />

A stint needs at least five clean-air laps, four distinct tyre-age values and a
span of at least four tyre-life laps on one compound. Driver results need at
least eight modelled laps. The Theil–Sen trend is fitted separately per stint;
residuals are then pooled per driver and race. Confidence depends only on sample
count, stint count and replay coverage—not on whether the result looks stable.

The slow-tail threshold is the larger of 0.75 seconds or 1% of the driver's
median eligible lap time. Only excess above that band contributes to cost. Even
after the clean-air and stint-trend controls, the result can contain car damage,
energy or tyre management, blue flags, local weather changes and feed errors.
</ExpandableSection>

<RelatedAnalysis section="drivers" current="pace-consistency" season={inputs.season.value} race={inputs.race.value} />
