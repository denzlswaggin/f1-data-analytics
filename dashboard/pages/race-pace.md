---
title: Where Was the Race Won?
hide_title: true
max_width: 1600
---

<AppNav />

<PageHeader
    eyebrow="Race analysis"
    title="Where was the race won?"
    description="Compare readable two-driver traces, controlled pace and stint phases using green-flag FastF1 timing."
/>

<KeyInsight label="How to read race pace">
Negative controlled deltas are faster. Compare two drivers on the same lap and compound instead of reading raw lap time alone.
</KeyInsight>

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
    'R' || lpad(cast(round as varchar), 2, '0') || ' · ' || replace(race_name, ' Grand Prix', '') as race_label
from f1.lap_times
where season = ${inputs.season.value}
order by round
```

<FilterBar title="Choose a race" description="The selection is preserved in links to related race analysis.">
    <Dropdown data={seasons} name=season value=season title="Season" />
    <DependentDropdown data={races} name=race value=round label=race_label order="round asc" title="Race" season={inputs.season.value} latest={true} preserveInitial={true} />
</FilterBar>

```sql pace_coverage
select * from f1.data_coverage
where section = 'race_pace'
    and season = cast(${inputs.season.value} as integer)
    and round = cast(${inputs.race.value} as integer)
```

<DataTrust data={pace_coverage} sampleLabel="green-flag laps" entityLabel="Drivers" method="descriptive, filtered timing" />

```sql drivers
select distinct season, round, driver_code
from f1.lap_times
where season = ${inputs.season.value} and round = ${inputs.race.value}
order by driver_code
```

<FilterBar title="Choose a duel" description="Two traces remain readable across a full race.">
    <DependentDropdown data={drivers} name=driver_a value=driver_code defaultValue="VER" title="Driver A" season={inputs.season.value} round={inputs.race.value} />
    <DependentDropdown data={drivers} name=driver_b value=driver_code defaultValue="LEC" title="Driver B" season={inputs.season.value} round={inputs.race.value} fallbackIndex={1} />
</FilterBar>

```sql race_laps
with contextual as (
    select
        *,
        avg(lap_time_sec) over (partition by lap_number, compound) as field_lap_avg_sec,
        count(*) over (partition by lap_number, compound) as field_lap_size
    from f1.lap_times
    where season = ${inputs.season.value} and round = ${inputs.race.value}
)
select
    driver_code,
    lap_number,
    compound,
    lap_time_sec - field_lap_avg_sec as controlled_delta_sec
from contextual
where field_lap_size >= 3
    and driver_code in ('${inputs.driver_a.value}', '${inputs.driver_b.value}')
order by driver_code, lap_number
```

## Controlled pace duel — {inputs.season.value} {inputs.race.label}

The chart subtracts the field average on the **same race lap and compound**,
controlling fuel load and compound choice. Negative values are faster than the
comparison field; two selected drivers stay readable throughout the race.

<LineChart
    data={race_laps}
    x=lap_number
    y=controlled_delta_sec
    series=driver_code
    yAxisTitle="delta to same-lap/compound field (s)"
    chartAreaHeight=360
>
    <ReferenceLine y=0 label="field average" />
</LineChart>

```sql phase_pace
with race as (
    select
        *,
        max(lap_number) over () as race_laps,
        avg(lap_time_sec) over (partition by lap_number, compound) as field_lap_avg_sec,
        count(*) over (partition by lap_number, compound) as field_lap_size
    from f1.lap_times
    where season = ${inputs.season.value} and round = ${inputs.race.value}
),
phased as (
    select
        driver_code,
        case
            when lap_number <= race_laps * 0.25 then 'Opening'
            when lap_number <= race_laps * 0.70 then 'Middle'
            else 'Closing'
        end as race_phase,
        lap_time_sec - field_lap_avg_sec as controlled_delta_sec
    from race
    where field_lap_size >= 3
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
<BarChart
    data={phase_pace}
    x=driver_code
    y=controlled_delta_sec
    series=race_phase
    type=grouped
    yAxisTitle="controlled pace delta (s) — lower is faster"
>
    <ReferenceLine y=0 label="field average" />
</BarChart>

<DataTable data={phase_pace} rows=60 search=true>
    <Column id=driver_code title="Driver" />
    <Column id=race_phase title="Phase" />
    <Column id=controlled_delta_sec title="Delta (s)" fmt="+0.000;-0.000" />
    <Column id=comparable_laps title="Laps" />
</DataTable>
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

<ExpandableSection title="Compare tyre-stint pace by compound">
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

<BarChart
    data={race_deg}
    x=compound
    y=deg_sec_per_lap
    yAxisTitle="observed slope (s/lap)"
    labels=true
    sort=false
/>
</ExpandableSection>

<RelatedAnalysis section="race" current="race-pace" season={inputs.season.value} race={inputs.race.value} />
