---
title: F1 Analytics — See Beyond the Result
hide_title: true
max_width: 1600
---

<AppNav />

<PageHeader
    hero={true}
    eyebrow="Performance analytics"
    title="Explore the data behind an F1 race"
    description="Choose a question, inspect the result, and follow the evidence behind each comparison."
>
    <div slot="actions">
        <a href="/f1-data-analytics/race-cockpit/">Explore a race</a>
        <a href="/f1-data-analytics/driver-comparison/">Compare drivers</a>
    </div>
</PageHeader>

```sql snapshot
select * from f1.snapshot_metadata
```

<SnapshotStatus data={snapshot} />

## Start with a question

Each analysis shows its data coverage and links to the observations behind its results.
Choose a starting point below, or browse the full set of analyses.

<InsightNav />

```sql latest_race
select * from f1.latest_race
```

```sql latest_story
select *
from f1.race_story
where race_label = (select race_label from ${latest_race})
```

```sql pace_leader
select driver_name
from ${latest_story}
where pace_rank is not null
order by pace_rank
limit 1
```

## Latest published race

### {latest_race[0].race_label}

These signals describe different parts of the race. The fastest loaded green lap is
one eligible lap, while the lowest observed peer delta compares repeatable pace
against other drivers on matching laps and tyres.

<div class="metric-grid">
<BigValue data={latest_race} value=fastest_driver title="Fastest loaded green lap" />
{#if pace_leader.length > 0}
<BigValue data={pace_leader} value=driver_name title="Lowest observed peer delta" />
{:else}
<p>No supported pace comparison in this race.</p>
{/if}
<BigValue data={latest_race} value=overtakes title="Detected passes" />
</div>

<RaceContextLink season={latest_race[0].season} race={latest_race[0].round} label="Open the latest race overview" />

Detected passes come from an experimental timing model and are not independently
verified overtakes. The [race overview](race-cockpit) explains which drivers and laps
support its comparisons.

The [current analytical evidence summary](methodology/#current-analytical-evidence)
shows snapshot-derived candidate and eligible counts, with historical validation
kept separate from current coverage.

## Data available for the latest race

```sql latest_coverage
select case section
    when 'race_story' then 'Recorded results and pace'
    when 'race_pace' then 'Green-flag lap timing'
    when 'telemetry' then 'Telemetry lap selections'
    when 'traffic_pace' then 'Traffic and clean-air pace'
    when 'tyre_warmup' then 'Tyre pace settling'
    when 'pit_window' then 'Pit-window comparisons'
    when 'race_control' then 'Race-control events'
    else replace(section, '_', ' ') end as analysis,
    sample_rows, sample_unit, usable_samples, usable_unit
from f1.data_coverage
where season = (select season from ${latest_race})
    and round = (select round from ${latest_race})
    and section in ('race_story', 'race_pace', 'telemetry', 'traffic_pace',
                    'tyre_warmup', 'pit_window', 'race_control')
order by analysis
```

Availability differs by analysis. Counts show published evidence, not accuracy;
missing sections have no published coverage record. Open a page for its exact
selection, eligibility filters and exclusions.

<div style="overflow-x: auto; max-width: 100%;">
<DataTable data={latest_coverage} rows=10>
    <Column id=analysis title="Analysis" />
    <Column id=sample_rows title="Input count" />
    <Column id=sample_unit title="Input unit" />
    <Column id=usable_samples title="Usable count" />
    <Column id=usable_unit title="Usable unit" />
</DataTable>
</div>

[Explore teammate-normalised driver ratings](driver-ratings) or
[compare two drivers](driver-comparison). These are model estimates within the
observed teammate network; they do not fully separate driver and car performance.

---

Published from an immutable snapshot generated at
<Value data={snapshot} column=generated_at fmt="yyyy-mm-dd HH:MM" />. Latest event:
<Value data={snapshot} column=latest_event_date />.
