---
title: Weather & Straight-Line Speed
---

Two race-day readouts pulled from FastF1 timing that the Ergast feed can't give
you: who carries the most speed down the longest straight, and how tyre
degradation shifts with track conditions.

```sql races
select distinct race_label
from f1.speed_trap
order by race_label desc
```

<Dropdown data={races} name=race value=race_label defaultValue="2024 Bahrain Grand Prix" />

## Straight-line speed — {inputs.race.value}

Fastest speed-trap reading on the longest straight (SpeedST), over green-flag
laps. A rough proxy for power-unit output and low-drag efficiency.

```sql race_speed
select
    driver_name,
    team,
    top_speed_kph,
    avg_speed_kph
from f1.speed_trap
where race_label = '${inputs.race.value}'
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

<DataTable data={race_speed} rows=12>
    <Column id=driver_name title="Driver" />
    <Column id=team title="Team" />
    <Column id=top_speed_kph title="Top (km/h)" fmt='0.0' />
    <Column id=avg_speed_kph title="Avg (km/h)" fmt='0.0' />
</DataTable>

## Tyre degradation by track conditions

Across every race with weather data, the average fall-off per compound in each
condition bucket (cool / hot / wet). Softer compounds and hotter tracks should
degrade faster.

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
    yAxisTitle="avg degradation (s/lap)"
/>

<DataTable data={deg_by_weather}>
    <Column id=compound title="Compound" />
    <Column id=weather_bucket title="Conditions" />
    <Column id=avg_deg_sec_per_lap title="Avg deg (s/lap)" fmt='0.000' />
    <Column id=laps title="Laps" />
</DataTable>
