---
title: Latest Published Race
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
    eyebrow="Latest published race"
    title={race[0]?.race_label || 'No published race'}
    description="Open the race cockpit for the recorded result, pace comparisons, strategy and evidence coverage."
/>

<SnapshotStatus data={snapshot} />

{#if race.length > 0}
<RaceContextLink season={race[0].season} race={race[0].round} label="Open this race in the cockpit" />

The cockpit is the shared race overview. Its race selector also opens earlier
rounds, with the same evidence definitions and missing-data states.

<RelatedAnalysis section="race" current="latest-race" season={race[0].season} race={race[0].round} />
{:else}
No race is available in this snapshot.
{/if}
