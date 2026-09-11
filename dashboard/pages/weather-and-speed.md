---
title: How Did Conditions Shape Performance?
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
    and race_label = (
        select race_label
        from f1.speed_trap
        where season = ${inputs.season.value} and round = ${inputs.race.value}
        limit 1
    )
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
<DataTable data={race_speed} rows=12>
    <Column id=driver_name title="Driver" />
    <Column id=team title="Team" />
    <Column id=top_speed_kph title="Top (km/h)" fmt='0.0' />
    <Column id=avg_speed_kph title="Avg (km/h)" fmt='0.0' />
</DataTable>
</ExpandableSection>

## Observed lap-time slope by track conditions

```sql weather_coverage
select * from f1.data_coverage where section = 'weather_slope'
```

<DataTrust data={weather_coverage} sampleLabel="compound-race fits" entityLabel="Compounds" method="descriptive; weather-covered races only" />

For races with weather coverage, this is the average unadjusted lap-time slope
per compound in each condition bucket (cool / hot / wet). It mixes tyre wear with
fuel burn, traffic and track evolution and is therefore descriptive only.

```sql deg_by_weather
select
    compound,
    weather_bucket,
    round(avg(deg_sec_per_lap), 3) as avg_deg_sec_per_lap,
    sum(n_laps) as laps
from f1.weather_degradation
where weather_bucket is not null
group by compound, weather_bucket
order by compound, weather_bucket
```

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

<ExpandableSection title="View weather slope data">
<DataTable data={deg_by_weather}>
    <Column id=compound title="Compound" />
    <Column id=weather_bucket title="Conditions" />
    <Column id=avg_deg_sec_per_lap title="Avg slope (s/lap)" fmt='0.000' />
    <Column id=laps title="Laps" />
</DataTable>
</ExpandableSection>

<RelatedAnalysis section="race" current="weather-and-speed" season={inputs.season.value} race={inputs.race.value} />
