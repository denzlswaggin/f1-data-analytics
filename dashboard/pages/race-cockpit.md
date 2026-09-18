---
title: Race Cockpit
hide_title: true
max_width: 1600
---

<AppNav />

<PageHeader
    eyebrow="Race cockpit"
    title="What happened — and where the result came from."
    description="Recorded results alongside pace comparisons, strategy context and experimental pass detections."
    accent="race"
>
    <div slot="actions">
        <RaceContextLink path="race-replay" season={inputs.season.value} race={inputs.race.value} label="Watch selected race" />
        <a href="/f1-data-analytics/methodology/">How to trust this</a>
    </div>
</PageHeader>

```sql snapshot
select * from f1.snapshot_metadata
```

<SnapshotStatus data={snapshot} />

```sql seasons
select distinct season from f1.race_story where season > 0 order by season desc
```

```sql races
select distinct season, round, race_name,
    'R' || lpad(cast(cast(round as integer) as varchar), 2, '0') || ' · '
        || replace(race_name, ' Grand Prix', '') as race_label
from f1.race_story
where season = ${inputs.season.value}
order by round
```

<FilterBar title="Choose a race" description="Every panel below stays on the same season and round.">
    <QueryDropdown data={seasons} name=season value=season title="Season" />
    <DependentDropdown data={races} name=race value=round label=race_label order="round asc" title="Race" season={inputs.season.value} latest={true} preserveInitial={true} />
</FilterBar>

```sql coverage
select * from f1.data_coverage
where section = 'race_story'
    and season = cast(${inputs.season.value} as integer)
    and round = cast(${inputs.race.value} as integer)
```

<DataTrust data={coverage} sampleLabel="driver summaries" entityLabel="Drivers" method="joined descriptive race evidence" />

```sql story
select * from f1.race_story
where season = ${inputs.season.value} and round = ${inputs.race.value}
```

```sql evidence_counts
select count(*) as result_drivers, count(pace_rank) as pace_drivers,
    count(passes_made) as pass_drivers from ${story}
```

```sql winner
select driver_name, grid_position, pace_rank, passes_made
from ${story} where finish_position = 1
```

```sql pace_leader
select driver_name, controlled_pace_delta_sec
from ${story} where pace_rank is not null order by pace_rank limit 1
```

```sql execution_leader
select driver_name, outcome_vs_pace
from ${story} where is_classified and outcome_vs_pace is not null
order by outcome_vs_pace desc, finish_position limit 1
```

```sql pass_leader
select driver_name, passes_made
from ${story} where passes_made is not null order by passes_made desc, finish_position limit 1
```

## What happened

<Grid cols=4>
    <BigValue data={winner} value=driver_name comparison=grid_position comparisonFmt="Grid P0" title="Winner" />
{#if pace_leader.length > 0}
    <BigValue data={pace_leader} value=driver_name title="Lowest observed peer delta" />
{:else}
<p>No supported pace comparison in this race.</p>
{/if}
{#if execution_leader.length > 0}
    <BigValue data={execution_leader} value=driver_name comparison=outcome_vs_pace comparisonFmt="+0;-0 vs pace" title="Largest finish/model difference" />
{:else}
<p>Finish/model comparison unavailable: incomplete pace field.</p>
{/if}
{#if pass_leader.length > 0}
    <BigValue data={pass_leader} value=driver_name comparison=passes_made comparisonFmt="0 passes" title="Most model-detected passes" />
{:else}
<p>Pass analysis unavailable for this race.</p>
{/if}
</Grid>

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

## Pace comparison and recorded finish

```sql outcome_flow
select driver_name, grid_position, pace_rank, finish_position, outcome_vs_pace
from ${story}
where is_classified
order by finish_position
```

<RaceOutcomeFlow data={outcome_flow} />

The middle position is a rank of observed peer-relative pace. The
last step also contains reliability, penalties, pit timing, traffic and race
incidents, so the flow is diagnostic rather than causal.

## Strategy and race-control observations

```sql strategy_summary
select count(*) filter (where eligible) as windows,
    count(*) filter (where eligible and position_flip) as flips,
    max(abs(net_time_gain_sec)) filter (where eligible) as largest_swing
from f1.pit_window_effectiveness
where season = ${inputs.season.value} and round = ${inputs.race.value}
having count(*) filter (where eligible) > 0
```

```sql control_summary
select c.event_count as interventions,
    coalesce(sum(e.intervention_stop_count), 0) as stops_under_control,
    coalesce(sum(e.position_gainer_count), 0) as observed_gainers
from f1.race_control_races c
left join f1.race_control_events e on e.season = c.season and e.round = c.round
where c.season = ${inputs.season.value} and c.round = ${inputs.race.value}
    and c.message_count > 0
group by c.event_count
```

```sql pass_summary
select detected_passes as passes
from f1.racecraft_coverage
where coverage_status in ('Processed', 'Processed: no observed battles')
    and season = ${inputs.season.value} and round = ${inputs.race.value}
```

<Grid cols=3>
    {#if strategy_summary.length > 0}
    <BigValue data={strategy_summary} value=flips comparison=largest_swing comparisonFmt="0.00 s max swing" title="Pit-window flips" />
    {:else}
    <p>No eligible pit-window comparison.</p>
    {/if}
    {#if control_summary.length > 0}
    <BigValue data={control_summary} value=interventions comparison=stops_under_control comparisonFmt="0 stops" title="Published interventions" />
    {:else}
    <p>Race-control source coverage unavailable.</p>
    {/if}
    {#if pass_summary.length > 0}
    <BigValue data={pass_summary} value=passes title="Model-detected passes" />
    {:else}
    <div>Pass analysis unavailable for this race.</div>
    {/if}
</Grid>

Pass counts are reconstructed model events; their event accuracy is unverified.

```sql strongest_windows
select early_driver_code || ' → ' || late_driver_code as matchup,
    net_time_gain_sec, outcome_label, confidence
from f1.pit_window_effectiveness
where season = ${inputs.season.value} and round = ${inputs.race.value} and eligible
order by abs(net_time_gain_sec) desc limit 8
```

```sql intervention_mix
select event_type, count(*) as events, sum(intervention_stop_count) as stops
from f1.race_control_events
where season = ${inputs.season.value} and round = ${inputs.race.value}
group by event_type order by events desc
```

<Grid cols=2>
{#if strongest_windows.length > 0}
<BarChart data={strongest_windows} x=matchup y=net_time_gain_sec series=outcome_label title="Largest observed pit-window swings" swapXY=true sort=false>
    <ReferenceLine y=0 label="no swing" />
</BarChart>
{:else}
<p>No eligible pit-window comparison.</p>
{/if}
{#if intervention_mix.length > 0}
<BarChart data={intervention_mix} x=event_type y=events title="Race-control interventions" labels=true />
{:else}
<p>No published intervention events. See Race Control for audited source coverage.</p>
{/if}
</Grid>

## Evidence trail

<ExpandableSection title="View the joined driver evidence">
<DataTable data={story} rows=22 search=true download=true>
    <Column id=finish_position title="Finish" />
    <Column id=driver_name title="Driver" />
    <Column id=grid_position title="Grid" />
    <Column id=pace_rank title="Pace rank" />
    <Column id=outcome_vs_pace title="vs pace" fmt="+0;-0" />
    <Column id=passes_made title="Passes made" />
    <Column id=passes_lost title="Passes lost" />
    <Column id=stops title="Recorded pit visits" />
    <Column id=story_label title="Interpretation" />
</DataTable>
</ExpandableSection>

<RelatedAnalysis section="race" current="race-cockpit" season={inputs.season.value} race={inputs.race.value} />
