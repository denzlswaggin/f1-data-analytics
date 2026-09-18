---
title: Who Won the Pit Window?
hide_title: true
max_width: 1600
---

<AppNav />

<PageHeader
    eyebrow="Strategy analysis"
    title="Who won the pit window?"
    description="Measure the observed time swing between nearby rivals who stopped on different laps, then separate recorded pit-lane duration from the rest of the cycle."
    accent="strategy"
/>

<KeyInsight label="How to read this">
A positive swing means the earlier-stopping driver gained time by the time both cars completed their out-laps. A completed undercut or overcut is only labelled when their order actually flips. This is observed pairwise evidence, not proof that strategy alone caused the swing.
</KeyInsight>

```sql seasons
select distinct season
from f1.pit_window_effectiveness
where season > 0
order by season desc
```

```sql races
select distinct
    season,
    round,
    race_name,
    'R' || lpad(cast(round as varchar), 2, '0') || ' · '
        || replace(race_name, ' Grand Prix', '') as race_label
from f1.pit_window_effectiveness
where season = ${inputs.season.value}
order by round
```

<FilterBar title="Choose a race" description="Only staggered stops between direct rivals are compared.">
    <Dropdown data={seasons} name=season value=season title="Season" />
    <DependentDropdown data={races} name=race value=round label=race_label order="round asc" title="Race" season={inputs.season.value} latest={true} preserveInitial={true} />
</FilterBar>

```sql coverage
select * from f1.data_coverage
where section = 'pit_window'
    and season = cast(${inputs.season.value} as integer)
    and round = cast(${inputs.race.value} as integer)
```

<DataTrust data={coverage} sampleLabel="candidate windows" entityLabel="Matchups" method="descriptive pairwise cycle; green-flag only" />

```sql race_matchups
select
    *,
    early_driver_code || ' → ' || late_driver_code as matchup
from f1.pit_window_effectiveness
where season = ${inputs.season.value} and round = ${inputs.race.value}
order by early_pit_lap, early_driver_code, late_driver_code
```

```sql eligible_matchups
select * from ${race_matchups} where eligible
```

```sql strongest_early
select early_driver_code as beneficiary, matchup, net_time_gain_sec as gain_sec
from ${eligible_matchups}
where net_time_gain_sec > 0
order by gain_sec desc, matchup
limit 1
```

```sql strongest_late
select late_driver_code as beneficiary, matchup, -net_time_gain_sec as gain_sec
from ${eligible_matchups}
where net_time_gain_sec < 0
order by gain_sec desc, matchup
limit 1
```

```sql completed_moves
select count(*) as moves
from ${eligible_matchups}
where position_flip
```

<Grid cols=3>
    {#if strongest_early.length > 0}
    <BigValue data={strongest_early} value=beneficiary comparison=gain_sec comparisonFmt="0.00 s" title="Largest early-stop gain" />
    {:else}
    <KeyInsight label="No early-stop gain">No eligible window shows a positive gain for the early stopper.</KeyInsight>
    {/if}
    {#if strongest_late.length > 0}
    <BigValue data={strongest_late} value=beneficiary comparison=gain_sec comparisonFmt="0.00 s" title="Largest late-stop gain" />
    {:else}
    <KeyInsight label="No late-stop gain">No eligible window shows a positive gain for the late stopper.</KeyInsight>
    {/if}
    <BigValue data={completed_moves} value=moves title="Completed position flips" />
</Grid>

## Time swing after both out-laps — {inputs.season.value} {inputs.race.label}

Each bar starts with the signed gap on the lap before the first stop and ends on
the common lap after the later driver's out-lap. Positive values favour the
earlier stop; negative values favour the later stop.

```sql ranked_matchups
select *
from ${eligible_matchups}
order by abs(net_time_gain_sec) desc
limit 20
```

{#if ranked_matchups.length > 0}
<BarChart
    data={ranked_matchups}
    x=matchup
    y=net_time_gain_sec
    series=outcome_label
    yAxisTitle="observed early-stop swing (s)"
    swapXY=true
    labels=true
    sort=false
>
    <ReferenceLine y=0 label="no time swing" />
</BarChart>
{/if}

## Timing versus the rest of the pit cycle

The horizontal axis is the earlier driver's full pit-lane duration minus the
later driver's: a positive value means the earlier stop took longer. The vertical
axis adds this difference to the observed early-stop swing to remove its timing
contribution. This residual still includes tyre warm-up, traffic and driver pace;
it is not an isolated on-track, tyre or strategy effect.

Jolpica duration includes pit entry and exit and can include red-flag time. It is
not stationary service time and cannot isolate mechanic performance.
[Source definition](https://github.com/jolpica/jolpica-f1/blob/main/docs/endpoints/pitstops.md).

```sql decomposed
select * from ${eligible_matchups}
where on_track_gain_sec is not null
```

{#if decomposed.length > 0}
<ScatterPlot
    data={decomposed}
    x=stop_duration_delta_sec
    y=on_track_gain_sec
    series=confidence
    xAxisTitle="early minus late pit-lane duration (s)"
    yAxisTitle="residual swing after pit-lane-duration adjustment (s)"
    tooltipTitle=matchup
    pointSize=24
>
    <ReferenceLine x=0 label="equal pit-lane duration" />
    <ReferenceLine y=0 label="no remaining swing" />
</ScatterPlot>
{:else}
<KeyInsight label="No duration decomposition">No eligible window has the pit-lane durations needed for this comparison.</KeyInsight>
{/if}

## Pairwise evidence

{#if eligible_matchups.length > 0}
<DataTable data={eligible_matchups} rows=30 search=true download=true>
    <Column id=matchup title="Early → late" />
    <Column id=stop_number title="Stop" />
    <Column id=early_pit_lap title="Early lap" />
    <Column id=late_pit_lap title="Late lap" />
    <Column id=early_old_compound title="Early from" />
    <Column id=early_new_compound title="Early to" />
    <Column id=late_old_compound title="Late from" />
    <Column id=late_new_compound title="Late to" />
    <Column id=gap_before_sec title="Gap before (s)" fmt="+0.00;-0.00" />
    <Column id=gap_after_sec title="Gap after (s)" fmt="+0.00;-0.00" />
    <Column id=net_time_gain_sec title="Early-stop swing (s)" fmt="+0.00;-0.00" />
    <Column id=stop_duration_delta_sec title="Pit-lane duration Δ (s)" fmt="+0.00;-0.00" />
    <Column id=on_track_gain_sec title="Residual swing (s)" fmt="+0.00;-0.00" />
    <Column id=outcome_label title="Outcome" />
    <Column id=confidence title="Evidence" />
</DataTable>
{:else}
<KeyInsight label="No eligible pairwise window">
This race has no nearby rivals with a complete green-flag timing window under
the selected method. Excluded candidates remain available below.
</KeyInsight>
{/if}

```sql excluded_matchups
select * from ${race_matchups} where not eligible
```

<ExpandableSection title="See excluded windows and the pairwise method">
{#if excluded_matchups.length > 0}
<DataTable data={excluded_matchups} rows=30 search=true>
    <Column id=matchup title="Early → late" />
    <Column id=early_pit_lap title="Early lap" />
    <Column id=late_pit_lap title="Late lap" />
    <Column id=exclusion_reason title="Why excluded" />
</DataTable>
{:else}
No candidate windows were excluded for this race.
{/if}

Candidates must be adjacent before the first stop, within five seconds, and pit
one to three laps apart. Both cars need a complete timing window with only green
track status and no additional stop. The baseline is the end of the lap before
the first stop; the outcome is the end of the later driver's out-lap. High
confidence additionally requires a pre-gap within three seconds, a one- or
two-lap offset, the same new compound, fresh tyres and both pit-lane durations.
</ExpandableSection>

<RelatedAnalysis section="race" current="pit-window-effectiveness" season={inputs.season.value} race={inputs.race.value} />
