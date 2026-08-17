---
title: Race Replay — Live Track Map
---

Watch a Grand Prix replay: every car placed on the circuit at its **true position
on the shared race clock**, reconstructed from FastF1 positional telemetry. Press
play, scrub the timeline, or speed it up — the running order and intervals on the
left update live as the race unfolds, and the **race-control feed** on the right
plays flags, safety cars and penalties in sync. Click a car to follow it, scroll
to zoom, click the timeline markers to jump to key moments, and click a 📻 marker
to play **team radio** (where available). _2026 season._

```sql replay_races
select distinct race_name
from f1.race_replay_meta
order by race_name
```

<Dropdown data={replay_races} name=race value=race_name defaultValue="Canadian Grand Prix" />

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
where race_name = '${inputs.race.value}'
order by driver_code, t_s
```

```sql replay_meta
select driver_code, driver_name, team, team_color
from f1.race_replay_meta
where race_name = '${inputs.race.value}'
```

```sql race_ctrl
select t_s, category, flag, scope, message, driver_code
from f1.race_control
where race_name = '${inputs.race.value}'
order by t_s
```

```sql radio
select t_s, driver_code, recording_url
from f1.team_radio
where race_name = '${inputs.race.value}'
order by t_s
```

<TrackMap data={replay} meta={replay_meta} messages={race_ctrl} radio={radio} title={inputs.race.value} />

## How it's built

Each car's X/Y is sampled by FastF1 at ~5 Hz on the session clock but at slightly
different instants. A pure-numpy step (`analytics/replay.py`) interpolates every
car onto one uniform time grid, reconstructs lap progress from lap timing to rank
the field, and derives the time gaps — landing a lean `marts.race_replay` table
(one row per car per tick) that this page animates. The dots interpolate between
ticks in the browser for smooth motion.
