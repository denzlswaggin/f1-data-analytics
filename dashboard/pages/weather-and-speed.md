---
title: How Did Conditions Shape Performance?
hide_title: true
max_width: 1600
---

<AppNav />

<PageHeader
    eyebrow="Conditions lab"
    title="How did conditions shape performance?"
    description="Put straight-line speed and observed tyre fall-off into the temperature and weather context of the race."
    accent="strategy"
/>

<KeyInsight label="Keep the comparison honest">
Straight-line speed is descriptive, not a pure power-unit ranking. Weather slopes also include fuel, traffic and track evolution.
</KeyInsight>

```sql seasons
select distinct season
from f1.speed_trap
order by season desc
```

```sql races
select distinct
    season,
    round,
    race_name,
    'R' || lpad(cast(round as varchar), 2, '0') || ' · ' || replace(race_name, ' Grand Prix', '') as race_label
from f1.speed_trap
where season = ${inputs.season.value}
order by round
```

<FilterBar title="Choose a race" description="Compare straight-line speed in the selected event.">
    <Dropdown data={seasons} name=season value=season title="Season" />
    <DependentDropdown data={races} name=race value=round label=race_label order="round asc" title="Race" season={inputs.season.value} latest={true} preserveInitial={true} />
</FilterBar>

```sql speed_coverage
select * from f1.data_coverage
where section = 'speed_trap'
    and season = cast(${inputs.season.value} as integer)
    and round = cast(${inputs.race.value} as integer)
```

<DataTrust data={speed_coverage} sampleLabel="driver summaries" entityLabel="Drivers" method="descriptive speed-trap sample" />

## Straight-line speed — {inputs.season.value} {inputs.race.label}

Fastest speed-trap reading on the longest straight (SpeedST), over green-flag
laps. A rough proxy for power-unit output and low-drag efficiency.

```sql race_speed
select
    driver_name,
    team,
    top_speed_kph,
    avg_speed_kph
from f1.speed_trap
where season = ${inputs.season.value} and round = ${inputs.race.value}
order by top_speed_kph desc
```

<BarChart
    data={race_speed}
    x=driver_name
    y=top_speed_kph
    yAxisTitle="top speed (km/h)"
    swapXY=true
    labels=true
    sort=false
/>

<ExpandableSection title="View straight-line speed data">
<div style="overflow-x: auto; max-width: 100%;">
<DataTable data={race_speed} rows=12>
    <Column id=driver_name title="Driver" />
    <Column id=team title="Team" />
    <Column id=top_speed_kph title="Top (km/h)" fmt='0.0' />
    <Column id=avg_speed_kph title="Avg (km/h)" fmt='0.0' />
</DataTable>
</div>
</ExpandableSection>

## Observed lap-time slope by track conditions

```sql weather_seasons
select distinct season from f1.weather_degradation order by season desc
```

<Dropdown data={weather_seasons} name=weather_season value=season title="Weather season (independent of speed race)" />

```sql weather_coverage
select sum(sample_rows) as sample_rows, sum(usable_samples) as usable_samples,
    count(*) as race_count, min(first_season) as first_season, max(last_season) as last_season,
    max(latest_event_date) as latest_event_date,
    (select count(distinct compound) from f1.weather_degradation
     where season = ${inputs.weather_season.value}) as entity_count,
    'fits' as sample_unit, 'fits' as usable_unit
from f1.data_coverage where section = 'weather_slope'
    and season = ${inputs.weather_season.value}
```

<DataTrust data={weather_coverage} sampleLabel="compound-race fits" entityLabel="Compounds" method="descriptive; weather-covered races only" />

Weather is aligned to each lap on the session clock; missing observations remain unknown.
Groups need at least five distinct races. This is the average unadjusted lap-time slope
per compound in each condition bucket (cool / hot / wet). It mixes tyre wear with
fuel burn, traffic and track evolution and is therefore descriptive only.

```sql deg_by_weather
select
    compound,
    weather_bucket,
    round(avg(deg_sec_per_lap), 3) as avg_deg_sec_per_lap,
    count(distinct round) as races,
    sum(n_laps) as laps
from f1.weather_degradation
where weather_bucket is not null and deg_sec_per_lap is not null
    and season = ${inputs.weather_season.value}
group by compound, weather_bucket
having count(distinct round) >= 5
order by compound, weather_bucket
```

{#if deg_by_weather.length > 0}
<BarChart
    data={deg_by_weather}
    x=compound
    y=avg_deg_sec_per_lap
    series=weather_bucket
    type=grouped
    yAxisTitle="avg observed slope (s/lap)"
>
    <ReferenceLine y=0 label="stable lap-time slope" />
</BarChart>
{:else}
<KeyInsight label="More weather-covered races needed">No compound and condition group has five fitted races in this season. Individual fits remain below.</KeyInsight>
{/if}

{#if deg_by_weather.length > 0}
<ExpandableSection title="View weather slope data">
<div style="overflow-x: auto; max-width: 100%;">
<DataTable data={deg_by_weather}>
    <Column id=compound title="Compound" />
    <Column id=weather_bucket title="Conditions" />
    <Column id=avg_deg_sec_per_lap title="Avg slope (s/lap)" fmt='0.000' />
    <Column id=races title="Races" />
    <Column id=laps title="Laps" />
</DataTable>
</div>
</ExpandableSection>

{/if}

```sql weather_samples
select season, round, race_name, compound, weather_bucket, n_laps, deg_sec_per_lap
from f1.weather_degradation
where season = ${inputs.weather_season.value}
order by round, compound, weather_bucket
```

Individual fits remain available even when a group has fewer than five races.
Blank conditions mean no aligned weather sample.
<div style="overflow-x: auto; max-width: 100%;">
<DataTable data={weather_samples} rows=10 search=true />
</div>

<RelatedAnalysis section="race" current="weather-and-speed" season={inputs.season.value} race={inputs.race.value} />
