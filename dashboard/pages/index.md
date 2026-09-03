---
title: F1 Analytics — See Beyond the Result
max_width: 1600
---

<AppNav />

Results tell you **what happened**. This dashboard uses teammate-normalised pace,
controlled race laps, strategy, telemetry and replay data to help explain **why**.

```sql snapshot
select * from f1.snapshot_metadata
```

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
order by pace_rank
limit 1
```

## Latest published race

### {latest_race[0].race_label}

<BigValue data={latest_race} value=fastest_driver title="Fastest lap" />
<BigValue data={pace_leader} value=driver_name title="Strongest controlled pace" />
<BigValue data={latest_race} value=overtakes title="Detected passes" />

[Open the complete race story](latest-race) or [watch the replay](race-replay).

## Explore by question

<InsightNav />

```sql leaders
select driver_name, rating
from f1.driver_ratings
where n_comparisons >= 40
order by rating desc
limit 5
```

## Fastest beyond the car

<BarChart
    data={leaders}
    x=driver_name
    y=rating
    swapXY=true
    sort=false
    labels=true
    title="Teammate-normalised career rating"
/>

[Explore the full driver ratings](driver-ratings) or
[compare two drivers](driver-comparison).

---

Published from an immutable snapshot generated at
<Value data={snapshot} column=generated_at fmt="yyyy-mm-dd HH:MM" />. Latest event:
<Value data={snapshot} column=latest_event_date />.
