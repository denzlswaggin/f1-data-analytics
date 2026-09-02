---
title: Telemetry — Speed Traces & Track Map
---

Distance-resampled FastF1 car telemetry for each driver's **fastest race lap**.
Compare who carried more speed where, then see a single driver's racing line
coloured by gear. _FastF1 telemetry covers the current season to date._

```sql seasons
select distinct season
from f1.telemetry_fastest_lap
order by season desc
```

<Dropdown data={seasons} name=season value=season title="Season" />

```sql tel_races
select distinct round, race_name
from f1.telemetry_fastest_lap
where season = ${inputs.season.value}
order by round
```

<Dropdown data={tel_races} name=race value=round label=race_name title="Race" />

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

Speed vs lap distance for every driver's fastest lap. Braking zones show as the
dips; the fastest cars hold more speed through them.

```sql speed_trace
select
    driver_code,
    distance_m,
    speed_kph
from f1.telemetry_fastest_lap
where season = ${inputs.season.value} and round = ${inputs.race.value}
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

## Track map by gear

Pick a driver to draw their lap as a racing line, each point coloured by the gear
selected there — corners (low gears) and straights (high gears) separate cleanly.

```sql tel_drivers
select distinct driver_code, driver_name
from f1.telemetry_fastest_lap
where season = ${inputs.season.value} and round = ${inputs.race.value}
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
