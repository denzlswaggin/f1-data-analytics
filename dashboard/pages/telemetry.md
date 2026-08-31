---
title: Where Does Each Driver Gain Time?
---

Distance-resampled FastF1 car telemetry for each driver's **fastest race lap**.
Compare who carried more speed where, then see a single driver's racing line
coloured by gear. _FastF1 telemetry covers the current season to date._

```sql tel_races
select distinct race_label
from f1.telemetry_fastest_lap
order by race_label desc
```

<Dropdown data={tel_races} name=race value=race_label defaultValue="2024 Bahrain Grand Prix" />

```sql telemetry_coverage
select * from f1.data_coverage
where section = 'telemetry' and race_label = '${inputs.race.value}'
```

<DataTrust data={telemetry_coverage} sampleLabel="fastest-lap selections" entityLabel="Drivers" method="descriptive fastest-lap sample" />

## Speed trace — {inputs.race.value}

Pick two drivers. Limiting the trace to a duel makes braking, minimum speed and
acceleration differences readable instead of overlaying the entire field.

```sql duel_drivers
select distinct driver_code, driver_name
from f1.telemetry_fastest_lap
where race_label = '${inputs.race.value}'
order by driver_code
```

<Dropdown data={duel_drivers} name=driver_a value=driver_code label=driver_name defaultValue="VER" title="Driver A" />
<Dropdown data={duel_drivers} name=driver_b value=driver_code label=driver_name defaultValue="LEC" title="Driver B" />

```sql speed_trace
select
    driver_code,
    distance_m,
    speed_kph
from f1.telemetry_fastest_lap
where race_label = '${inputs.race.value}'
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
    where race_label = '${inputs.race.value}'
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
where race_label = '${inputs.race.value}'
    and driver_code in ('${inputs.driver_a.value}', '${inputs.driver_b.value}')
order by driver_code, distance_m
```

## Pedal inputs

<LineChart
    data={inputs_trace}
    x=distance_m
    y=throttle
    series=driver_code
    xAxisTitle="lap distance (m)"
    yAxisTitle="throttle (%)"
    chartAreaHeight=240
/>

## Track map by gear

Pick a driver to draw their lap as a racing line, each point coloured by the gear
selected there — corners (low gears) and straights (high gears) separate cleanly.

```sql tel_drivers
select distinct driver_code, driver_name
from f1.telemetry_fastest_lap
where race_label = '${inputs.race.value}'
order by driver_code
```

<Dropdown data={tel_drivers} name=driver value=driver_code label=driver_name />

```sql track
select
    x,
    y,
    gear,
    speed_kph
from f1.telemetry_fastest_lap
where race_label = '${inputs.race.value}'
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
