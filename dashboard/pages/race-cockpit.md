---
title: Race Cockpit
hide_title: true
max_width: 1600
---

<AppNav />

<PageHeader
    eyebrow="Race cockpit"
    title="What happened — and where the result came from."
    description="One race-level view joining controlled pace, execution, strategy, race control and on-track passing."
    accent="race"
>
    <div slot="actions">
        <a href="/f1-data-analytics/race-replay/">Watch selected race</a>
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
    'R' || lpad(cast(round as varchar), 2, '0') || ' · '
        || replace(race_name, ' Grand Prix', '') as race_label
from f1.race_story
where season = ${inputs.season.value}
order by round
```

<FilterBar title="Choose a race" description="Every panel below stays on the same season and round.">
    <Dropdown data={seasons} name=season value=season title="Season" />
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

```sql winner
select driver_name, grid_position, pace_rank, passes_made
from ${story} where finish_position = 1
```

```sql pace_leader
select driver_name, controlled_pace_delta_sec
from ${story} order by pace_rank limit 1
```

```sql execution_leader
select driver_name, outcome_vs_pace
from ${story} where is_classified
order by outcome_vs_pace desc, finish_position limit 1
```

```sql pass_leader
select driver_name, passes_made
from ${story} order by passes_made desc, finish_position limit 1
```

## What happened

<Grid cols=4>
    <BigValue data={winner} value=driver_name comparison=grid_position comparisonFmt="Grid P0" title="Winner" />
    <BigValue data={pace_leader} value=driver_name title="Strongest controlled pace" />
    <BigValue data={execution_leader} value=driver_name comparison=outcome_vs_pace comparisonFmt="+0;-0 vs pace" title="Best conversion" />
    <BigValue data={pass_leader} value=driver_name comparison=passes_made comparisonFmt="0 passes" title="Most on-track passes" />
</Grid>

<KeyInsight label="Race in one sentence">
<Value data={winner} column=driver_name /> won from grid position
<Value data={winner} column=grid_position />, while controlled pace favoured
<Value data={pace_leader} column=driver_name />. <Value data={execution_leader} column=driver_name />
finished <Value data={execution_leader} column=outcome_vs_pace fmt="+0;-0" /> places versus
their pace rank, and <Value data={pass_leader} column=driver_name /> made
<Value data={pass_leader} column=passes_made /> detected passes.
</KeyInsight>

## How pace became the result

```sql outcome_flow
select driver_name, grid_position, pace_rank, finish_position, outcome_vs_pace
from ${story}
where is_classified
order by finish_position
```

<RaceOutcomeFlow data={outcome_flow} />

The middle position is based on same-lap, same-compound controlled pace. The
last step also contains reliability, penalties, pit timing, traffic and race
incidents, so the flow is diagnostic rather than causal.

## Why the order changed

```sql strategy_summary
select count(*) filter (where eligible) as windows,
    count(*) filter (where eligible and position_flip) as flips,
    max(abs(net_time_gain_sec)) filter (where eligible) as largest_swing
from f1.pit_window_effectiveness
where season = ${inputs.season.value} and round = ${inputs.race.value}
```

```sql control_summary
select count(*) as interventions,
    coalesce(sum(intervention_stop_count), 0) as stops_under_control,
    coalesce(sum(position_gainer_count), 0) as observed_gainers
from f1.race_control_events
where season = ${inputs.season.value} and round = ${inputs.race.value}
```

```sql pass_summary
select count(*) as passes, round(avg(confidence) * 100, 0) as average_confidence_pct
from f1.race_overtakes
where season = ${inputs.season.value} and round = ${inputs.race.value}
```

<Grid cols=3>
    <BigValue data={strategy_summary} value=flips comparison=largest_swing comparisonFmt="0.00 s max swing" title="Pit-window flips" />
    <BigValue data={control_summary} value=interventions comparison=stops_under_control comparisonFmt="0 stops" title="Neutralisations" />
    <BigValue data={pass_summary} value=passes comparison=average_confidence_pct comparisonFmt="0% avg confidence" title="Detected passes" />
</Grid>

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
<BarChart data={strongest_windows} x=matchup y=net_time_gain_sec series=outcome_label title="Largest observed pit-window swings" swapXY=true sort=false>
    <ReferenceLine y=0 label="no swing" />
</BarChart>
<BarChart data={intervention_mix} x=event_type y=events title="Race-control interventions" labels=true />
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
    <Column id=stops />
    <Column id=story_label title="Interpretation" />
</DataTable>
</ExpandableSection>

<RelatedAnalysis section="race" current="race-cockpit" season={inputs.season.value} race={inputs.race.value} />
