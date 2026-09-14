select
    season,
    round,
    race_name,
    event_id,
    event_number,
    event_type,
    driver_code,
    driver_name,
    team,
    checkpoint_type,
    checkpoint_order,
    checkpoint_t_s,
    lap_number,
    lap_progress,
    running_order,
    gap_to_leader_s,
    stint,
    compound,
    tyre_life,
    capture_offset_s,
    source,
    eligible,
    exclusion_reason,
    methodology_version
from marts.race_control_checkpoints

union all
select
    0, 0, '__NO_DATA__', '__NO_DATA__', 0, 'No event', '__NO_DATA__',
    'No driver', 'No team', 'unavailable', 0, cast(null as double),
    cast(null as integer), cast(null as double), cast(null as integer),
    cast(null as double), cast(null as integer), '', cast(null as integer),
    cast(null as double), 'unavailable', false, 'No data', 'race-control-impact-v3'
where not exists (select 1 from marts.race_control_checkpoints)
order by season, round, event_number, driver_code, checkpoint_order
