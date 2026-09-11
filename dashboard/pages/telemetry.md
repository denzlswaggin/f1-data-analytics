---
title: Where Does Each Driver Gain Time?
max_width: 1600
---

<AppNav />

<PageHeader
    eyebrow="Telemetry lab"
    title="Where does each driver gain time?"
    description="Overlay fastest-race-lap speed, cumulative delta and pedal inputs, then map the selected gear around the circuit."
    accent="drivers"
/>

<KeyInsight label="How to compare laps">
Use the cumulative delta to find where time was gained; use speed and pedal traces to explain how it was gained.
</KeyInsight>

```sql seasons
select distinct season
from f1.telemetry_fastest_lap
order by season desc
```

```sql tel_races
select distinct
    season,
    round,
    race_name,
    'R' || lpad(cast(round as varchar), 2, '0') || ' · ' || replace(race_name, ' Grand Prix', '') as race_label
from f1.telemetry_fastest_lap
where season = ${inputs.season.value}
order by round
```

<FilterBar title="Choose a race" description="Fastest-lap telemetry coverage varies by season.">
    <Dropdown data={seasons} name=season value=season title="Season" />
    <DependentDropdown data={tel_races} name=race value=round label=race_label order="round asc" title="Race" season={inputs.season.value} latest={true} preserveInitial={true} />
</FilterBar>

```sql telemetry_coverage
select * from f1.data_coverage
where section = 'telemetry'
    and race_label = (
        select race_label
        from f1.telemetry_fastest_lap
        where season = ${inputs.season.value} and round = ${inputs.race.value}
        limit 1
    )
```

<DataTrust data={telemetry_coverage} sampleLabel="fastest-lap selections" entityLabel="Drivers" method="descriptive fastest-lap sample" />

## Speed trace — {inputs.season.value} {inputs.race.label}

Pick two drivers. Limiting the trace to a duel makes braking, minimum speed and
acceleration differences readable instead of overlaying the entire field.

```sql duel_drivers
select distinct season, round, driver_code, driver_name
from f1.telemetry_fastest_lap
where season = ${inputs.season.value} and round = ${inputs.race.value}
order by driver_code
```

<FilterBar title="Choose a duel" description="Compare two fastest race laps point by point.">
    <DependentDropdown data={duel_drivers} name=driver_a value=driver_code label=driver_name defaultValue="VER" title="Driver A" season={inputs.season.value} round={inputs.race.value} />
    <DependentDropdown data={duel_drivers} name=driver_b value=driver_code label=driver_name defaultValue="LEC" title="Driver B" season={inputs.season.value} round={inputs.race.value} fallbackIndex={1} />
</FilterBar>

```sql speed_trace
select
    driver_code,
    distance_m,
    speed_kph
from f1.telemetry_fastest_lap
where season = ${inputs.season.value} and round = ${inputs.race.value}
    and driver_code in ('${inputs.driver_a.value}', '${inputs.driver_b.value}')
order by driver_code, distance_m
```

<LineChart
    data={speed_trace}
    x=distance_m
    y=speed_kph
    series=driver_code
    xAxisTitle="lap distance (m)"
    yAxisTitle="speed (km/h)"
    chartAreaHeight=360
/>

```sql time_delta
with ordered as (
    select
        driver_code,
        distance_m,
        speed_kph,
        lag(distance_m) over (partition by driver_code order by distance_m) as prev_distance_m,
        lag(speed_kph) over (partition by driver_code order by distance_m) as prev_speed_kph
    from f1.telemetry_fastest_lap
    where season = ${inputs.season.value} and round = ${inputs.race.value}
        and driver_code in ('${inputs.driver_a.value}', '${inputs.driver_b.value}')
),
segments as (
    select
        driver_code,
        distance_m,
        case
            when prev_distance_m is null or speed_kph + prev_speed_kph <= 0 then 0
            else 7.2 * (distance_m - prev_distance_m) / (speed_kph + prev_speed_kph)
        end as segment_sec
    from ordered
),
elapsed as (
    select
        driver_code,
        distance_m,
        sum(segment_sec) over (
            partition by driver_code order by distance_m rows unbounded preceding
        ) as elapsed_sec
    from segments
),
driver_a as (
    select distance_m, elapsed_sec
    from elapsed
    where driver_code = '${inputs.driver_a.value}'
),
driver_b as (
    select distance_m, elapsed_sec
    from elapsed
    where driver_code = '${inputs.driver_b.value}'
)
select
    driver_a.distance_m,
    driver_b.elapsed_sec - driver_a.elapsed_sec as delta_sec
from driver_a
inner join driver_b using (distance_m)
order by distance_m
```

## Where the lap was won

The line accumulates time from the speed traces. Positive means Driver B is behind
Driver A; a rising section is where A gains, and a falling section is where B gains.

<LineChart
    data={time_delta}
    x=distance_m
    y=delta_sec
    xAxisTitle="lap distance (m)"
    yAxisTitle="Driver B − Driver A (s)"
    chartAreaHeight=300
>
    <ReferenceLine y=0 label="level" />
</LineChart>

```sql inputs_trace
select driver_code, distance_m, throttle, brake
from f1.telemetry_fastest_lap
where season = ${inputs.season.value} and round = ${inputs.race.value}
    and driver_code in ('${inputs.driver_a.value}', '${inputs.driver_b.value}')
order by driver_code, distance_m
```

<ExpandableSection title="Compare pedal inputs">
<LineChart
    data={inputs_trace}
    x=distance_m
    y=throttle
    series=driver_code
    xAxisTitle="lap distance (m)"
    yAxisTitle="throttle (%)"
    chartAreaHeight=240
/>
</ExpandableSection>

## Track map by gear

Pick a driver to draw their lap as a racing line, each point coloured by the gear
selected there — corners (low gears) and straights (high gears) separate cleanly.

```sql tel_drivers
select distinct season, round, driver_code, driver_name
from f1.telemetry_fastest_lap
where season = ${inputs.season.value} and round = ${inputs.race.value}
order by driver_code
```

<FilterBar title="Choose a driver" description="Colour the racing line by selected gear.">
    <DependentDropdown data={tel_drivers} name=driver value=driver_code label=driver_name title="Driver" season={inputs.season.value} round={inputs.race.value} />
</FilterBar>

```sql track
select
    x,
    y,
    gear,
    speed_kph
from f1.telemetry_fastest_lap
where season = ${inputs.season.value} and round = ${inputs.race.value}
    and driver_code = '${inputs.driver.value}'
order by distance_m
```

<ScatterPlot
    data={track}
    x=x
    y=y
    series=gear
    pointSize=10
    xAxisTitle=""
    yAxisTitle=""
/>

<RelatedAnalysis section="race" current="telemetry" season={inputs.season.value} race={inputs.race.value} />
