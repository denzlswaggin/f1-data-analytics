---
title: How the Latest Race Unfolded
---

<AppNav />

```sql snapshot
select * from f1.snapshot_metadata
```

```sql race
select * from f1.latest_race
```

# {race[0].race_label}

This is the newest fully transformed race in the published snapshot. Data was
exported at <Value data={snapshot} column=generated_at fmt="yyyy-mm-dd HH:MM" />;
the newest represented event is <Value data={snapshot} column=latest_event_date />.

<BigValue data={race} value=drivers title="Drivers" />
<BigValue data={race} value=fastest_driver title="Fastest lap" />
<BigValue data={race} value=fastest_lap_sec title="Lap time" fmt="0.000" />
<BigValue data={race} value=overtakes title="Detected passes" />

```sql story_coverage
select * from f1.data_coverage
where section = 'race_story' and race_label = (select race_label from ${race})
```

<DataTrust data={story_coverage} sampleLabel="driver summaries" entityLabel="Drivers" method="same-lap, same-compound controlled pace" />

```sql story
select *
from f1.race_story
where race_label = (select race_label from ${race})
```

```sql winner
select driver_name, pace_rank, grid_position, finish_position
from ${story}
where finish_position = 1
```

```sql pace_leader
select driver_name, controlled_pace_delta_sec
from ${story}
order by pace_rank
limit 1
```

```sql execution_gain
select driver_name, outcome_vs_pace
from ${story}
where is_classified
order by outcome_vs_pace desc, finish_position
limit 1
```

```sql pass_leader
select driver_name, passes_made
from ${story}
order by passes_made desc, finish_position
limit 1
```

## The race story

<BigValue data={pace_leader} value=driver_name title="Strongest controlled pace" />
<BigValue data={execution_gain} value=driver_name title="Biggest execution gain" />
<BigValue data={pass_leader} value=driver_name title="Most on-track passes" />

<KeyInsight label="Race in one sentence">
The winner, <Value data={winner} column=driver_name />, ranked
**P<Value data={winner} column=pace_rank />** on same-lap, same-compound pace.
<Value data={execution_gain} column=driver_name /> finished
<Value data={execution_gain} column=outcome_vs_pace fmt="+0;-0" /> positions ahead of
their controlled-pace rank, while <Value data={pass_leader} column=driver_name /> made
<Value data={pass_leader} column=passes_made /> detected on-track passes.
</KeyInsight>

```sql execution_chart
select driver_name, outcome_vs_pace, story_label
from ${story}
where is_classified
order by outcome_vs_pace desc
```

<BarChart
    data={execution_chart}
    x=driver_name
    y=outcome_vs_pace
    series=story_label
    swapXY=true
    sort=false
    xAxisTitle="finish positions versus controlled pace rank"
/>

Positive means the driver finished ahead of their controlled-pace rank; negative
means pace was not converted into the result. Reliability, penalties and race
context still matter, so this is an execution signal rather than a causal score.

## Driver-by-driver evidence

<ExpandableSection title="View driver-by-driver evidence">
<DataTable data={story} rows=22 search=true>
    <Column id=finish_position title="Finish" />
    <Column id=driver_name title="Driver" />
    <Column id=grid_position title="Grid" />
    <Column id=pace_rank title="Pace rank" />
    <Column id=outcome_vs_pace title="vs pace" fmt="+0;-0" />
    <Column id=passes_made title="Passes" />
    <Column id=stops />
    <Column id=story_label title="Interpretation" />
</DataTable>
</ExpandableSection>

## Data at a glance

<ExpandableSection title="View snapshot details">
<DataTable data={race} rows=1 download=true>
    <Column id=race_label title="Race" />
    <Column id=lap_rows title="Clean lap rows" />
    <Column id=stints />
    <Column id=compounds />
    <Column id=air_temp title="Air °C" fmt="0.0" />
    <Column id=track_temp title="Track °C" fmt="0.0" />
    <Column id=replay_duration_sec title="Replay seconds" fmt="0" />
</DataTable>
</ExpandableSection>

<RelatedAnalysis section="race" current="latest-race" />
