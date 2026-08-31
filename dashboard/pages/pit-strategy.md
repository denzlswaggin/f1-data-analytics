---
title: Pit-Cycle Position Swings
---

This page describes a driver's track position the lap **before** each stop versus
**two laps after**, alongside the stop's stationary time. Positive means places
were gained across that window. It is not a counterfactual undercut/overcut
estimate: rival stops, SC/VSC periods, retirements and lapped cars can all move the
observed position. Ergast-sourced (pit-stop timing from ~2011).

```sql races
select distinct race_label
from f1.pit_strategy
order by race_label desc
```

<Dropdown data={races} name=race value=race_label defaultValue="2024 Bahrain Grand Prix" />

```sql pit_coverage
select * from f1.data_coverage
where section = 'pit_cycle' and race_label = '${inputs.race.value}'
```

<DataTrust data={pit_coverage} sampleLabel="pit stops" entityLabel="Drivers" method="descriptive window; not counterfactual" />

```sql race_stops
select
    driver_name,
    stop_number,
    pit_lap,
    duration_sec,
    position_before,
    position_after,
    positions_gained
from f1.pit_strategy
where race_label = '${inputs.race.value}'
order by pit_lap
```

```sql impact
select *
from f1.strategy_impact
where race_label = '${inputs.race.value}'
order by pit_lap
```

## Position swing across each stop — {inputs.race.value}

```sql driver_net
select
    driver_name,
    sum(positions_gained) as net_positions,
    count(*) as stops,
    round(avg(duration_sec), 2) as avg_stop_sec
from f1.pit_strategy
where race_label = '${inputs.race.value}'
    and positions_gained is not null
group by driver_name
order by net_positions desc
```

<BarChart
    data={driver_net}
    x=driver_name
    y=net_positions
    yAxisTitle="observed net position swing"
    swapXY=true
    labels=true
    sort=false
/>

## Stop speed versus cycle outcome

This separates two facts that the previous net-position number mixed together:
how quick the stationary stop was relative to the race average, and what happened
to track position across the cycle. Stops within two laps of a safety car, VSC or
red flag are labelled separately.

<ScatterPlot
    data={impact}
    x=stop_delta_sec
    y=positions_gained
    series=impact_label
    xAxisTitle="stationary time versus race average (s)"
    yAxisTitle="observed positions gained"
    tooltipTitle=driver_name
    pointSize=24
>
    <ReferenceLine x=0 label="race-average stop" />
    <ReferenceLine y=0 label="position held" />
</ScatterPlot>

## Every stop

<DataTable data={race_stops} rows=20>
    <Column id=driver_name title="Driver" />
    <Column id=stop_number title="Stop" />
    <Column id=pit_lap title="Lap" />
    <Column id=duration_sec title="Stationary (s)" fmt='0.00' />
    <Column id=position_before title="Pos before" />
    <Column id=position_after title="Pos after" />
    <Column id=positions_gained title="Gained" />
</DataTable>

## Evidence by stop

<DataTable data={impact} rows=30 search=true>
    <Column id=driver_name title="Driver" />
    <Column id=stop_number title="Stop" />
    <Column id=pit_lap title="Lap" />
    <Column id=duration_sec title="Stationary (s)" fmt='0.00' />
    <Column id=stop_delta_sec title="vs average" fmt='+0.00;-0.00' />
    <Column id=positions_gained title="Positions" fmt='+0;-0' />
    <Column id=impact_label title="Context" />
</DataTable>

Even a clean positive cycle is not automatically an undercut: rival stops,
traffic, tyre warm-up and retirements can still explain the movement. The chart
is designed to identify candidates for replay inspection, not award causal credit.
