---
title: Watch the Race Unfold
---

Watch a Grand Prix replay: every car placed on the circuit at its **true position
on the shared race clock**, reconstructed from FastF1 positional telemetry. Press
play, scrub the timeline, or speed it up — the running order and intervals on the
left update live as the race unfolds, and the **race-control feed** on the right
plays flags, safety cars and penalties in sync. Detected **on-track overtakes**
light up on the map as they happen and sit on their own ⇄ seek lane below. Click a
car to follow it (its overtakes and radio filter to that driver), scroll to zoom,
click the timeline markers to jump to key moments, and click a 📻 marker to play
**team radio** (where available). The picker contains every replay partition in
the currently published snapshot.

```sql replay_seasons
select distinct
    season,
    case when season = 0 then 'No replay data available' else cast(season as varchar) end as season_label
from f1.race_replay_meta
order by season desc
```

<Dropdown data={replay_seasons} name=season value=season label=season_label title="Season" />

```sql replay_races
select distinct
    round,
    case
        when race_name = '__NO_DATA__' then 'No replay data available'
        else replace(race_name, cast(season as varchar) || ' ', '')
    end as race_name
from f1.race_replay_meta
where season = ${inputs.season.value}
order by round
```

<Dropdown data={replay_races} name=race value=round label=race_name title="Race" />

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

<DataTrust data={replay_coverage} sampleLabel="car ticks" entityLabel="Drivers" method="reconstructed replay; experimental overtake detector" />

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

```sql replay_meta
select driver_code, driver_name, team, team_color
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
select t_s, for_position, passer_code, passed_code, gap_at_pass_s
from f1.race_overtakes
where season = ${inputs.season.value} and round = ${inputs.race.value}
    and passer_code <> '__NO_DATA__'
order by t_s
```

<TrackMap data={replay} meta={replay_meta} messages={race_ctrl} radio={radio} overtakes={overtakes} title={`${inputs.season.label} ${inputs.race.label}`} />

## How it's built

Each car's X/Y is sampled by FastF1 at ~5 Hz on the session clock but at slightly
different instants. A pure-numpy step (`analytics/replay.py`) interpolates every
car onto one uniform time grid, reconstructs lap progress from lap timing to rank
the field, and derives the time gaps — landing a lean `marts.race_replay` table
(one row per car per tick) that this page animates. The dots interpolate between
ticks in the browser for smooth motion.

A second pure step (`analytics/overtakes.py`) reads that replay feed and flags
**on-track overtakes** — a clean, single-position swap where the two cars are
physically side-by-side (which is what distinguishes a real pass from a pit-cycle
position change, since the pitting car's projected gap momentarily collapses too).
Those land in `marts.race_overtakes` and feed the ⇄ markers and the on-map
highlight above.
