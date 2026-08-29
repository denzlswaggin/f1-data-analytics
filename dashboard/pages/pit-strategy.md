---
title: Pit Strategy — Undercut & Overcut
---

Every pit stop is a gamble: box a lap early to jump a rival on fresh tyres (the
_undercut_), or stay out for clean air and clear them later (the _overcut_). This
page measures the outcome — a driver's track position the lap **before** each stop
versus **two laps after** — alongside the stop's stationary time. Positive =
places gained across the cycle. Ergast-sourced (pit-stop timing from ~2011).

```sql races
select distinct race_label
from f1.pit_strategy
order by race_label desc
```

<Dropdown data={races} name=race value=race_label defaultValue="2024 Bahrain Grand Prix" />

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
    yAxisTitle="net places gained across stops"
    swapXY=true
    labels=true
    sort=false
/>

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

## Quickest stops of the race

<DataTable data={driver_net} rows=10>
    <Column id=driver_name title="Driver" />
    <Column id=stops />
    <Column id=avg_stop_sec title="Avg stationary (s)" fmt='0.00' />
    <Column id=net_positions title="Net places" />
</DataTable>
