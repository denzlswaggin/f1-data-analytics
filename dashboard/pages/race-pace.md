---
title: Race Pace & Tyre Stints
---

Per-lap race pace from FastF1 timing data — green-flag laps only (safety-car and
yellow laps filtered out). Pick a race to see how pace evolved and where tyre
stints fall. _Sample: 2024, rounds 1–5._

```sql races
select distinct race_name
from f1.lap_times
order by race_name
```

<Dropdown data={races} name=race value=race_name defaultValue="Bahrain Grand Prix" />

```sql race_laps
select
    driver_code,
    lap_number,
    lap_time_sec,
    compound,
    stint,
    position
from f1.lap_times
where race_name = '${inputs.race.value}'
order by driver_code, lap_number
```

## Lap-time evolution — {inputs.race.value}

<LineChart
    data={race_laps}
    x=lap_number
    y=lap_time_sec
    series=driver_code
    yAxisTitle="lap time (s)"
    chartAreaHeight=360
/>

## Tyre-stint pace by compound

```sql compound_pace
select
    compound,
    count(*) as laps,
    round(min(lap_time_sec), 2) as best_lap_sec,
    round(avg(lap_time_sec), 2) as avg_lap_sec
from f1.lap_times
where race_name = '${inputs.race.value}'
group by compound
order by avg_lap_sec
```

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

## Tyre degradation — {inputs.race.value}

Pace lost per lap of tyre age (linear fit over green-flag laps). Higher =
faster fall-off; softer compounds should degrade quicker.

```sql race_deg
select
    compound,
    deg_sec_per_lap,
    n_laps
from f1.tyre_degradation
where race_name = '${inputs.race.value}'
order by deg_sec_per_lap desc
```

<BarChart
    data={race_deg}
    x=compound
    y=deg_sec_per_lap
    yAxisTitle="degradation (s/lap)"
    labels=true
    sort=false
/>
