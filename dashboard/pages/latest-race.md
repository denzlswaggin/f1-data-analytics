---
title: How the Latest Race Unfolded
hide_title: true
max_width: 1600
---

<AppNav />

```sql snapshot
select * from f1.snapshot_metadata
```

```sql race
select * from f1.latest_race
```

<PageHeader
    eyebrow="Latest race report"
    title={race[0].race_label}
    description="Recorded results, observed peer-relative pace and experimental pass detections."
>
    <div slot="actions">
        <a href="/f1-data-analytics/race-replay/">Watch replay</a>
        <a href="/f1-data-analytics/race-pace/">Open pace analysis</a>
    </div>
</PageHeader>

<SnapshotStatus data={snapshot} />

<div class="metric-grid">
<BigValue data={race} value=drivers title="Drivers" />
<BigValue data={race} value=fastest_driver title="Fastest loaded green lap" />
<BigValue data={race} value=fastest_lap_time title="Lap time" />
<BigValue data={race} value=overtakes title="Detected passes" />
</div>

```sql story_coverage
select * from f1.data_coverage
where section = 'race_story'
    and season = (select cast(season as integer) from ${race})
    and round = (select cast(round as integer) from ${race})
```

<DataTrust data={story_coverage} sampleLabel="driver summaries" entityLabel="Drivers" method="same-lap, same-compound controlled pace" />

```sql story
select *
from f1.race_story
where race_label = (select race_label from ${race})
```

```sql evidence_counts
select count(*) as result_drivers, count(pace_rank) as pace_drivers,
    count(passes_made) as pass_drivers from ${story}
```

```sql winner
select driver_name, pace_rank, grid_position, finish_position
from ${story}
where finish_position = 1
```

```sql pace_leader
select driver_name, controlled_pace_delta_sec
from ${story}
where pace_rank is not null
order by pace_rank
limit 1
```

```sql execution_gain
select driver_name, outcome_vs_pace
from ${story}
where is_classified and outcome_vs_pace is not null
order by outcome_vs_pace desc, finish_position
limit 1
```

```sql pass_leader
select driver_name, passes_made
from ${story}
where passes_made is not null
order by passes_made desc, finish_position
limit 1
```

## The race story

<div class="metric-grid">
{#if pace_leader.length > 0}
<BigValue data={pace_leader} value=driver_name title="Lowest observed peer delta" />
{:else}
<p>No supported pace comparison in this race.</p>
{/if}
{#if execution_gain.length > 0}
<BigValue data={execution_gain} value=driver_name title="Largest finish/model difference" />
{:else}
<p>Finish/model comparison unavailable: incomplete pace field.</p>
{/if}
{#if pass_leader.length > 0}
<BigValue data={pass_leader} value=driver_name title="Most model-detected passes" />
{:else}
<p>Pass analysis unavailable for this race.</p>
{/if}
</div>

<KeyInsight label="Reading the evidence">
Pace covers <Value data={evidence_counts} column=pace_drivers /> of
<Value data={evidence_counts} column=result_drivers /> result drivers; pass
analysis is available for <Value data={evidence_counts} column=pass_drivers />.
Pace is the median lap-time difference from at least three other drivers on the
same lap and compound, after shared pit-lap exclusions. At least five comparable
laps are required. Ranks cover eligible drivers only; finish/rank differences
are shown only when the entire result field has a pace estimate. These are
observed comparisons, not measurements of driver skill or execution. Pass counts
come from experimental timing reconstruction; missing analysis stays blank.
</KeyInsight>

```sql execution_chart
select driver_name, outcome_vs_pace, story_label
from ${story}
where is_classified and outcome_vs_pace is not null
order by outcome_vs_pace desc
```

{#if execution_chart.length > 0}
<BarChart
    data={execution_chart}
    x=driver_name
    y=outcome_vs_pace
    series=story_label
    swapXY=true
    sort=false
    xAxisTitle="finish positions versus controlled pace rank"
>
    <ReferenceLine y=0 label="matched pace rank" />
</BarChart>
{:else}
<p>A finish/model chart requires comparable pace for the complete result field.</p>
{/if}

Positive means the driver finished ahead of their controlled-pace rank; negative
means the recorded finish was behind the model rank. Reliability, penalties,
traffic and differing lap samples remain confounders; this is not an execution score.

## Driver-by-driver evidence

<ExpandableSection title="View driver-by-driver evidence">
<DataTable data={story} rows=22 search=true>
    <Column id=finish_position title="Finish" />
    <Column id=driver_name title="Driver" />
    <Column id=grid_position title="Grid" />
    <Column id=pace_rank title="Pace rank" />
    <Column id=outcome_vs_pace title="vs pace" fmt="+0;-0" />
    <Column id=passes_made title="Passes" />
    <Column id=stops title="Recorded pit visits" />
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
