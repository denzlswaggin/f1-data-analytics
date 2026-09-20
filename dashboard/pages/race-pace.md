---
title: Where Was the Race Won?
hide_title: true
max_width: 1600
---

<AppNav />

<PageHeader
    eyebrow="Race analysis"
    title="Where was the race won?"
    description="Compare readable two-driver traces, peer-relative pace and race phases using green-flag FastF1 timing."
/>

```sql seasons
select distinct season
from f1.lap_times
order by season desc
```

```sql races
select distinct
    season,
    round,
    race_name,
    'R' || lpad(cast(cast(round as integer) as varchar), 2, '0') || ' · ' || replace(race_name, ' Grand Prix', '') as race_label
from f1.lap_times
where season = ${inputs.season.value}
order by round
```

```sql pace_coverage
select coverage.* exclude (usable_samples, usable_unit),
    (select count(*) from f1.traffic_adjusted_laps
     where season = ${inputs.season.value} and round = ${inputs.race.value}
       and controlled_pace_delta_sec is not null) as usable_samples,
    'laps' as usable_unit
from f1.data_coverage as coverage
where section = 'race_pace'
    and season = cast(${inputs.season.value} as integer)
    and round = cast(${inputs.race.value} as integer)
```

```sql drivers
select distinct season, round, driver_code
from f1.lap_times
where season = ${inputs.season.value} and round = ${inputs.race.value}
order by driver_code
```

<FilterBar title="Race and drivers" description="Choose the race and two drivers for the pace comparison.">
    <QueryDropdown data={seasons} name=season value=season title="Season" />
    <DependentDropdown data={races} name=race value=round label=race_label order="round asc" title="Race" season={inputs.season.value} latest={true} preserveInitial={true} />
    <DependentDropdown data={drivers} name=driver_a value=driver_code defaultValue="VER" title="Driver A" season={inputs.season.value} round={inputs.race.value} />
    <DependentDropdown data={drivers} name=driver_b value=driver_code defaultValue="LEC" title="Driver B" season={inputs.season.value} round={inputs.race.value} fallbackIndex={1} />
</FilterBar>

```sql comparable_laps
select *
from f1.traffic_adjusted_laps
where season = ${inputs.season.value} and round = ${inputs.race.value}
    and controlled_pace_delta_sec is not null
```

```sql race_laps
select driver_code, lap_number, compound,
    controlled_pace_delta_sec as controlled_delta_sec
from ${comparable_laps}
where driver_code in ('${inputs.driver_a.value}', '${inputs.driver_b.value}')
order by driver_code, lap_number
```

## Peer-relative pace duel

Negative values mean faster than the same-lap, same-compound peer median.
Tyre age, traffic and car performance can still differ.

{#if race_laps.length > 0}
<LineChart
    data={race_laps}
    x=lap_number
    y=controlled_delta_sec
    series=driver_code
    yAxisTitle="delta to other-driver median (s)"
    chartAreaHeight=360
>
    <ReferenceLine y=0 label="peer median" />
</LineChart>
{:else}
<KeyInsight label="No comparable laps for this duel">
The shared baseline has no eligible laps for these drivers in this race.
Historical timing remains available in the raw compound summaries below;
missing replay coverage is not evidence of equal pace.
</KeyInsight>
{/if}

<KeyInsight label="How to read race pace">
Negative deltas mean faster than the median of at least three other drivers on the same race lap and compound. This is the shared Traffic and Consistency baseline; it does not isolate driver skill or remove tyre-age and traffic effects.
</KeyInsight>

<DataTrust data={pace_coverage} sampleLabel="green-flag laps" entityLabel="Drivers" method="shared leave-one-driver-out median; at least three peers" />

<ExpandableSection title="Data & methodology: eligible laps and peer baseline">
The baseline excludes the selected driver and uses the median of at least three
other drivers on the same lap and compound. Lap one, pit transitions, unknown
compounds and tyres younger than two laps are excluded by the shared model.
Replay context is required by this published dataset. Same-lap matching reduces
some race-phase differences; fuel loads, tyre age, car performance and traffic
can still differ. Different compounds also mean different comparison groups.
</ExpandableSection>

```sql phase_pace
with race as (
    select *,
        (select max(lap_number) from f1.lap_times
         where season = ${inputs.season.value} and round = ${inputs.race.value}) as race_laps
    from ${comparable_laps}
),
phased as (
    select
        driver_code,
        case
            when lap_number <= race_laps * 0.25 then 'Opening'
            when lap_number <= race_laps * 0.70 then 'Middle'
            else 'Closing'
        end as race_phase,
        controlled_pace_delta_sec as controlled_delta_sec
    from race
)
select
    driver_code,
    race_phase,
    avg(controlled_delta_sec) as controlled_delta_sec,
    count(*) as comparable_laps
from phased
group by driver_code, race_phase
having count(*) >= 5
order by race_phase, controlled_delta_sec
```

<ExpandableSection title="Compare every driver by race phase">
Each phase requires at least five comparable laps per driver. Phase boundaries use the last published timing lap.

{#if phase_pace.length > 0}
<BarChart
    data={phase_pace}
    x=driver_code
    y=controlled_delta_sec
    series=race_phase
    type=grouped
    yAxisTitle="peer-relative delta (s) — lower is faster"
>
    <ReferenceLine y=0 label="peer median" />
</BarChart>

<DataTable data={phase_pace} rows=60 search=true>
    <Column id=driver_code title="Driver" />
    <Column id=race_phase title="Phase" />
    <Column id=controlled_delta_sec title="Delta (s)" fmt="+0.000;-0.000" />
    <Column id=comparable_laps title="Laps" />
</DataTable>
{:else}
No driver phase reaches five comparable laps.
{/if}
</ExpandableSection>

```sql compound_pace
select
    compound,
    count(*) as laps,
    round(min(lap_time_sec), 2) as best_lap_sec,
    round(avg(lap_time_sec), 2) as avg_lap_sec
from f1.lap_times
where season = ${inputs.season.value} and round = ${inputs.race.value}
group by compound
order by avg_lap_sec
```

<ExpandableSection title="Compare raw pace by compound">
These are unadjusted timing summaries. Differences include race phase, car, driver, tyre age and traffic; they do not measure a compound advantage.
<BarChart
    data={compound_pace}
    x=compound
    y=avg_lap_sec
    yAxisTitle="avg green-flag lap (s)"
    labels=true
    sort=false
/>

<DataTable data={compound_pace}>
    <Column id=compound title="Compound" />
    <Column id=laps />
    <Column id=best_lap_sec title="Best (s)" fmt='0.00' />
    <Column id=avg_lap_sec title="Avg (s)" fmt='0.00' />
</DataTable>
</ExpandableSection>

```sql race_deg
select
    compound,
    deg_sec_per_lap,
    n_laps
from f1.tyre_degradation
where season = ${inputs.season.value} and round = ${inputs.race.value}
order by deg_sec_per_lap desc
```

<ExpandableSection title="Inspect observed lap-time slope vs tyre age">
Linear slope of lap time against tyre age over green-flag laps. Positive means
laps became slower as the set aged; negative means they became faster. This
descriptive slope is not adjusted for fuel burn, traffic or track evolution.

{#if race_deg.length > 0}
<BarChart
    data={race_deg}
    x=compound
    y=deg_sec_per_lap
    yAxisTitle="observed slope (s/lap)"
    labels=true
    sort=false
/>
{:else}
No tyre-age slope is available for this race.
{/if}
</ExpandableSection>

<RelatedAnalysis section="race" current="race-pace" season={inputs.season.value} race={inputs.race.value} />
