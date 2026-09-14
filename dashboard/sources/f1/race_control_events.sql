select
    season,
    round,
    race_name,
    'R' || lpad(cast(round as varchar), 2, '0') || ' · '
        || replace(race_name, ' Grand Prix', '') as race_label,
    event_id,
    event_number,
    event_type,
    start_t_s,
    end_t_s,
    post_checkpoint_t_s,
    deployment_lap,
    end_lap,
    post_checkpoint_lap,
    duration_s,
    event_status,
    recovery_clean,
    pre_driver_count,
    post_driver_count,
    eligible_driver_count,
    time_comparable_driver_count,
    time_eligible,
    time_exclusion_reason,
    intervention_stop_count,
    recovery_stop_count,
    position_gainer_count,
    position_loser_count,
    position_status,
    gap_status,
    pit_status,
    restart_status,
    tyre_status,
    focus_driver_code,
    eligible,
    exclusion_reason,
    confidence,
    methodology_version
from marts.race_control_events

-- Evidence 40 cannot serialise an empty source. The internal season-zero row is
-- removed by every user-facing query.
union all
select
    0, 0, '__NO_DATA__', 'R00 · No data', '__NO_DATA__', 0, 'No event',
    cast(null as double), cast(null as double), cast(null as double),
    cast(null as integer), cast(null as integer), cast(null as integer),
    cast(null as double), 'unavailable', false,
    0, 0, 0, 0, false, 'No data', 0, 0, 0, 0,
    'unavailable', 'unavailable', 'unavailable', 'unavailable', 'unavailable', '__NO_DATA__',
    false, 'No data', 'Low', 'race-control-impact-v3'
where not exists (select 1 from marts.race_control_events)
order by season, round, event_number
