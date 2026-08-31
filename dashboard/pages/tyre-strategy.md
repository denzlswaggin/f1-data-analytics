---
title: Which Tyres Faded?
---

Who ran which compound, for how long, and when they pitted — the classic F1
**strategy chart**. Each row is a driver (ordered by finish), each coloured block a
tyre stint on the true race-lap axis; a vertical tick marks every pit stop, and each
stint **darkens toward its end in proportion to its observed within-stint pace
slope** (s/lap). The slope is descriptive and not adjusted for fuel, traffic or
track evolution. Built from FastF1 per-lap compound + stint data. _Hover a stint
for its lap range, tyre age, and observed slope._

```sql races
select distinct race_label
from f1.stint_strategy
order by race_label desc
```

<Dropdown data={races} name=race value=race_label defaultValue="2024 Bahrain Grand Prix" />

```sql tyre_coverage
select * from f1.data_coverage
where section = 'tyre_strategy' and race_label = '${inputs.race.value}'
```

<DataTrust data={tyre_coverage} sampleLabel="stints" entityLabel="Drivers" method="descriptive, unadjusted slope" />

```sql race_stints
select *
from f1.stint_strategy
where race_label = '${inputs.race.value}'
order by finish_position, stint
```

<StintChart data={race_stints} title={inputs.race.value} />

## Fuel- and track-adjusted fall-off

Each lap is compared with other cars on the **same race lap and compound** before
the tyre-age slope is fitted. This removes much of the shared fuel-burn and track-
evolution trend that makes raw lap times look like tyre degradation.

```sql adjusted_deg
select *
from f1.adjusted_stint_degradation
where race_label = '${inputs.race.value}'
```

<ScatterPlot
    data={adjusted_deg}
    x=stint_length
    y=adjusted_deg_sec_per_lap
    series=compound
    xAxisTitle="comparable stint span (laps)"
    yAxisTitle="adjusted fall-off (s/lap)"
    tooltipTitle=driver_name
    pointSize=24
>
    <ReferenceLine y=0 label="stable residual pace" />
</ScatterPlot>

```sql cliff_stints
select *
from ${adjusted_deg}
where cliff_signal
order by late_stint_loss_sec desc
```

<DataTable data={adjusted_deg} rows=40 search=true>
    <Column id=driver_code title="Driver" />
    <Column id=stint />
    <Column id=compound />
    <Column id=stint_length title="Span" />
    <Column id=adjusted_deg_sec_per_lap title="Adjusted s/lap" fmt="+0.000;-0.000" />
    <Column id=raw_deg_sec_per_lap title="Raw s/lap" fmt="+0.000;-0.000" />
    <Column id=late_stint_loss_sec title="Late loss (s)" fmt="+0.00;-0.00" />
    <Column id=cliff_signal title="Cliff" />
</DataTable>

The cliff flag requires at least 0.8 seconds of residual loss between the first
and final three comparable laps. It is a review signal, not a tyre-failure forecast.

## Strategy summary — {inputs.race.value}

Number of stops and the compound sequence each driver ran, in finishing order.

```sql strategies
select
    min(finish_position) as pos,
    driver_code,
    driver_name,
    count(*) - 1 as stops,
    string_agg(compound, ' → ' order by stint) as strategy
from f1.stint_strategy
where race_label = '${inputs.race.value}'
group by driver_code, driver_name
order by pos
```

<DataTable data={strategies} rows=20>
    <Column id=pos title="Pos" align=center />
    <Column id=driver_code title="Driver" />
    <Column id=stops title="Stops" align=center />
    <Column id=strategy title="Compound sequence" />
</DataTable>
