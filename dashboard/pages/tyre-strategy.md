---
title: Tyre Strategy
---

Who ran which compound, for how long, and when they pitted — the classic F1
**strategy chart**. Each row is a driver (ordered by finish), each coloured block a
tyre stint on the true race-lap axis; a vertical tick marks every pit stop, and each
stint **darkens toward its end in proportion to how fast the tyre fell off**
(degradation, s/lap). Built from FastF1 per-lap compound + stint data. _Hover a stint
for its lap range, tyre age, and fall-off._

```sql races
select distinct race_label
from f1.stint_strategy
order by race_label desc
```

<Dropdown data={races} name=race value=race_label defaultValue="2024 Bahrain Grand Prix" />

```sql race_stints
select *
from f1.stint_strategy
where race_label = '${inputs.race.value}'
order by finish_position, stint
```

<StintChart data={race_stints} title={inputs.race.value} />

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
