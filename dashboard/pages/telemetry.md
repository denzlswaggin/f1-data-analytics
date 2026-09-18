---
title: Where Does Each Driver Gain Time?
hide_title: true
max_width: 1600
---

<AppNav />

<PageHeader
    eyebrow="Telemetry lab"
    title="Where does each driver gain time?"
    description="Compare jointly matched race laps with tyre and race-lap context, then inspect speed, estimated time delta and pedal inputs."
    accent="drivers"
/>

<KeyInsight label="How to compare laps">
The duel requires the same dry compound, green track status and no more than three laps of difference in race lap or tyre age. Traces describe the selected laps; car performance, traffic and driver choices remain mixed.
</KeyInsight>

```sql seasons
select distinct season
from f1.telemetry_laps
order by season desc
```

```sql tel_races
select distinct
    season,
    round,
    race_name,
    'R' || lpad(cast(cast(round as integer) as varchar), 2, '0') || ' · ' || replace(race_name, ' Grand Prix', '') as race_label
from f1.telemetry_laps
where season = ${inputs.season.value}
order by round
```

<FilterBar title="Choose a race" description="Matched-lap telemetry coverage varies by race.">
    <QueryDropdown data={seasons} name=season value=season title="Season" />
    <DependentDropdown data={tel_races} name=race value=round label=race_label order="round asc" title="Race" season={inputs.season.value} latest={true} preserveInitial={true} />
</FilterBar>

```sql telemetry_coverage
select coverage.* exclude (sample_rows, usable_samples),
    (select count(distinct (driver_code, lap_number)) from f1.telemetry_laps
     where season = ${inputs.season.value} and round = ${inputs.race.value}) as sample_rows,
    cast(null as bigint) as usable_samples
from f1.data_coverage as coverage
where section = 'telemetry'
    and season = cast(${inputs.season.value} as integer)
    and round = cast(${inputs.race.value} as integer)
```

<DataTrust data={telemetry_coverage} sampleLabel="driver selections" entityLabel="Drivers" method="selected telemetry laps; joint context matching" />

## Speed trace — {inputs.season.value} {inputs.race.label}

The published pool contains each driver's fastest available timed lap and eligible
Driver DNA teammate laps. It is a sample, not every race lap. Pick two drivers. Limiting the trace to a duel makes braking, minimum speed and
acceleration differences readable instead of overlaying the entire field.

```sql duel_drivers
select distinct season, round, driver_code, driver_name
from f1.telemetry_laps
where season = ${inputs.season.value} and round = ${inputs.race.value}
order by driver_code
```

<FilterBar title="Choose a duel" description="Select the closest supported fast-lap pair from the published pool.">
    <DependentDropdown data={duel_drivers} name=driver_a value=driver_code label=driver_name defaultValue="VER" title="Driver A" season={inputs.season.value} round={inputs.race.value} />
    <DependentDropdown data={duel_drivers} name=driver_b value=driver_code label=driver_name defaultValue="LEC" title="Driver B" season={inputs.season.value} round={inputs.race.value} fallbackIndex={1} />
</FilterBar>

```sql candidate_laps
select driver_code, lap_number, compound, tyre_life, track_status, lap_time_sec,
    count(distinct distance_m) as points
from f1.telemetry_laps
where season = ${inputs.season.value} and round = ${inputs.race.value}
    and driver_code in ('${inputs.driver_a.value}', '${inputs.driver_b.value}')
    and pit_in_time_sec is null and pit_out_time_sec is null
    and lap_number > 1 and tyre_life >= 2
    and track_status = '1' and compound in ('SOFT', 'MEDIUM', 'HARD')
    and lap_time_sec > 0
group by driver_code, lap_number, compound, tyre_life, track_status, lap_time_sec
having count(distinct distance_m) >= 100
```

```sql matched_pair
select a.driver_code as driver_a, b.driver_code as driver_b,
    a.lap_number as lap_a, b.lap_number as lap_b, a.compound,
    a.tyre_life as tyre_age_a, b.tyre_life as tyre_age_b,
    a.lap_time_sec as time_a, b.lap_time_sec as time_b
from ${candidate_laps} a
join ${candidate_laps} b on a.compound = b.compound
    and abs(a.lap_number - b.lap_number) <= 3
    and abs(a.tyre_life - b.tyre_life) <= 3
where a.driver_code = '${inputs.driver_a.value}'
    and b.driver_code = '${inputs.driver_b.value}'
    and a.driver_code <> b.driver_code
order by a.lap_time_sec + b.lap_time_sec
    + 0.03 * abs(a.lap_number - b.lap_number)
    + 0.03 * abs(a.tyre_life - b.tyre_life), a.lap_number, b.lap_number
limit 1
```

```sql selected_telemetry
select t.*
from f1.telemetry_laps t
join ${matched_pair} p on
    (t.driver_code = p.driver_a and t.lap_number = p.lap_a)
    or (t.driver_code = p.driver_b and t.lap_number = p.lap_b)
where t.season = ${inputs.season.value} and t.round = ${inputs.race.value}
```

{#if matched_pair.length > 0}
<div style="overflow-x: auto; max-width: 100%;">
<DataTable data={matched_pair}>
    <Column id=driver_a title="Driver A" />
    <Column id=lap_a title="Lap A" />
    <Column id=tyre_age_a title="Tyre age A" />
    <Column id=time_a title="Lap A (s)" fmt="0.000" />
    <Column id=driver_b title="Driver B" />
    <Column id=lap_b title="Lap B" />
    <Column id=tyre_age_b title="Tyre age B" />
    <Column id=time_b title="Lap B (s)" fmt="0.000" />
    <Column id=compound title="Compound" />
</DataTable>
</div>
{:else}
<KeyInsight label="No matched lap pair">
Choose two different drivers. No pair in the published pool meets the compound,
track-status, tyre-age and race-lap limits for this selection. Individual fastest
available lap maps remain below; unmatched laps are not compared as a duel.
</KeyInsight>
{/if}

```sql speed_trace
select
    driver_code,
    distance_m,
    speed_kph
from ${selected_telemetry}
where season = ${inputs.season.value} and round = ${inputs.race.value}
    and driver_code in ('${inputs.driver_a.value}', '${inputs.driver_b.value}')
order by driver_code, distance_m
```

{#if speed_trace.length > 0}
<LineChart
    data={speed_trace}
    x=distance_m
    y=speed_kph
    series=driver_code
    xAxisTitle="lap distance (m)"
    yAxisTitle="speed (km/h)"
    chartAreaHeight=360
/>
{/if}

```sql time_delta
with ordered as (
    select
        driver_code,
        distance_m,
        speed_kph,
        lag(distance_m) over (partition by driver_code order by distance_m) as prev_distance_m,
        lag(speed_kph) over (partition by driver_code order by distance_m) as prev_speed_kph
    from ${selected_telemetry}
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

## Estimated time difference along the lap

The line integrates resampled speed over distance. It is an approximation, not official split timing. Only common distance samples are compared; differing lap endpoints and interpolation can change the final delta. Positive means Driver B is behind
Driver A; a rising section is where A gains, and a falling section is where B gains.

{#if time_delta.length > 0}
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
{/if}

```sql inputs_trace
select driver_code, distance_m, throttle, brake
from ${selected_telemetry}
where season = ${inputs.season.value} and round = ${inputs.race.value}
    and driver_code in ('${inputs.driver_a.value}', '${inputs.driver_b.value}')
order by driver_code, distance_m
```

<ExpandableSection title="Compare pedal inputs">
{#if inputs_trace.length > 0}
<LineChart
    data={inputs_trace}
    x=distance_m
    y=throttle
    series=driver_code
    xAxisTitle="lap distance (m)"
    yAxisTitle="throttle (%)"
    chartAreaHeight=240
/>
<LineChart
    data={inputs_trace}
    x=distance_m
    y=brake
    series=driver_code
    xAxisTitle="lap distance (m)"
    yAxisTitle="brake applied (0/1)"
    chartAreaHeight=180
/>
{/if}
</ExpandableSection>

## Track map by gear

Pick a driver to draw their fastest available timed lap as a racing line, each point coloured by the gear
selected there — corners (low gears) and straights (high gears) separate cleanly.

```sql tel_drivers
select distinct season, round, driver_code, driver_name
from f1.telemetry_laps
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
from f1.telemetry_laps
where season = ${inputs.season.value} and round = ${inputs.race.value}
    and driver_code = '${inputs.driver.value}'
    and is_fastest_available
order by distance_m
```

{#if track.length > 0}
<ScatterPlot
    data={track}
    x=x
    y=y
    series=gear
    pointSize=10
    xAxisTitle=""
    yAxisTitle=""
/>
{:else}
No individual fastest-lap map is available for this driver.
{/if}

<RelatedAnalysis section="race" current="telemetry" season={inputs.season.value} race={inputs.race.value} />
