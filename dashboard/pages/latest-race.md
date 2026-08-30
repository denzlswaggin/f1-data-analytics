---
title: Latest Race
---

```sql snapshot
select * from f1.snapshot_metadata
```

```sql race
select * from f1.latest_race
```

# {race[0].race_label}

This is the newest fully transformed race in the published snapshot. Data was
exported at <Value data={snapshot} column=generated_at fmt="yyyy-mm-dd HH:MM" />;
the newest represented event is <Value data={snapshot} column=latest_event_date />.

<BigValue data={race} value=drivers title="Drivers" />
<BigValue data={race} value=fastest_driver title="Fastest lap" />
<BigValue data={race} value=fastest_lap_sec title="Lap time" fmt="0.000" />
<BigValue data={race} value=overtakes title="Detected passes" />

## Weekend at a glance

<DataTable data={race} rows=1 download=true>
    <Column id=race_label title="Race" />
    <Column id=lap_rows title="Clean lap rows" />
    <Column id=stints />
    <Column id=compounds />
    <Column id=air_temp title="Air °C" fmt="0.0" />
    <Column id=track_temp title="Track °C" fmt="0.0" />
    <Column id=replay_duration_sec title="Replay seconds" fmt="0" />
</DataTable>

Continue with the [race replay](race-replay), [race pace](race-pace),
[tyre strategy](tyre-strategy), or [telemetry comparison](telemetry). Each page
defaults to the newest partition it actually contains and states its coverage.
