---
title: Watch the Race Unfold
---

<AppNav />

Replay every car on a shared race clock reconstructed from FastF1 positional
telemetry. Running order, race control, overtakes and available radio stay in sync.
Only full-race position feeds are published; a truncated upstream feed is withheld
instead of presenting a partial race as a complete replay.

<KeyInsight label="Replay controls">
Press play or scrub the timeline. Use Space to play or pause and the arrow keys to
move five seconds. Select a car for its live lap, tyre and gap detail. The unified
timeline filters race control, detected passes and radio, then jumps to the exact moment.
</KeyInsight>

```sql replay_seasons
select distinct
    cast(season as integer) as season,
    case
        when season = 0 then 'No replay data available'
        else cast(cast(season as integer) as varchar)
    end as season_label
from f1.race_replay_meta
order by season desc
```

```sql replay_races
select distinct
    cast(season as integer) as season,
    cast(round as integer) as round,
    case
        when race_name = '__NO_DATA__' then 'No replay data available'
        else substr(race_name, strpos(race_name, ' ') + 1)
    end as race_name
from f1.race_replay_meta
order by season desc, round
```

<FilterBar title="Choose a replay" description="Only races available in the published snapshot are listed.">
    <ReplayRacePicker seasons={replay_seasons} races={replay_races} />
</FilterBar>

```sql replay_coverage
select * from f1.data_coverage
where section = 'race_replay'
    and race_label = (
        select race_name
        from f1.race_replay_meta
        where season = ${inputs.season.value} and round = ${inputs.race.value}
        limit 1
    )
```

<DataTrust data={replay_coverage} sampleLabel="car ticks" entityLabel="Drivers" method="reconstructed replay; confidence-scored pass detector" />

```sql replay
select
    driver_code,
    t_s,
    x,
    y,
    running_order,
    gap_to_leader_s,
    gap_to_ahead_s
from f1.race_replay
where season = ${inputs.season.value} and round = ${inputs.race.value}
    and driver_code <> '__NO_DATA__'
order by driver_code, t_s
```

```sql replay_laps
select driver_code, lap_number, lap_start_t_s, lap_time_sec, stint, compound, tyre_life
from f1.race_replay_laps
where season = ${inputs.season.value} and round = ${inputs.race.value}
order by driver_code, lap_number
```

```sql replay_meta
select
    driver_code,
    driver_name,
    team,
    team_color,
    grid_position,
    finish_position,
    status,
    is_classified
from f1.race_replay_meta
where season = ${inputs.season.value} and round = ${inputs.race.value}
    and driver_code <> '__NO_DATA__'
```

```sql race_ctrl
select t_s, category, flag, scope, message, driver_code
from f1.race_control
where season = ${inputs.season.value} and round = ${inputs.race.value}
order by t_s
```

```sql radio
select t_s, driver_code, recording_url, transcript
from f1.team_radio
where season = ${inputs.season.value} and round = ${inputs.race.value}
order by t_s
```

```sql overtakes
select t_s, for_position, passer_code, passed_code, gap_at_pass_s, confidence, evidence, reason
from f1.race_overtakes
where season = ${inputs.season.value} and round = ${inputs.race.value}
    and passer_code <> '__NO_DATA__'
order by t_s
```

<TrackMap data={replay} laps={replay_laps} meta={replay_meta} messages={race_ctrl} radio={radio} overtakes={overtakes} title={`${inputs.season.label} ${inputs.race.label}`} />

<ExpandableSection title="How the replay is built">
Each car's X/Y is sampled by FastF1 at ~5 Hz on the session clock but at slightly
different instants. A pure-numpy step (`analytics/replay.py`) interpolates every
car onto one uniform time grid, reconstructs lap progress from lap timing to rank
the field, and derives the time gaps — landing a lean `marts.race_replay` table
(one row per car per tick) that this page animates. The dots interpolate between
ticks in the browser for smooth motion.

A second pure step (`analytics/overtakes.py`) reads that replay feed and flags
**detected on-track overtakes**. It accepts a clean adjacent swap, including a
short timing-feed dropout, only when the cars are physically close and the new
order persists. Every accepted event includes a confidence score and its detector
evidence; pit-cycle position changes and ranking flicker remain excluded. Those
events feed the ⇄ markers and the on-map highlight above.

Before either mart is published, position timestamps are checked against the
lap-timing race window. Batch rebuilds skip any partition below 90% coverage and
report it explicitly, so an upstream outage cannot turn into a misleadingly short
race or overtake count.
</ExpandableSection>

<RelatedAnalysis section="race" current="race-replay" season={inputs.season.value} race={inputs.race.value} />
