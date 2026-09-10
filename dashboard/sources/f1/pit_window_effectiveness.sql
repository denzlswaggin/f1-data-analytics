select
    season,
    round,
    race_name,
    'R' || lpad(cast(round as varchar), 2, '0') || ' · '
        || replace(race_name, ' Grand Prix', '') as race_label,
    stop_number,
    early_driver_code,
    early_driver_name,
    early_team,
    late_driver_code,
    late_driver_name,
    late_team,
    early_pit_lap,
    late_pit_lap,
    stop_separation_laps,
    checkpoint_before_lap,
    checkpoint_after_lap,
    early_old_compound,
    early_new_compound,
    late_old_compound,
    late_new_compound,
    early_new_tyre_fresh,
    late_new_tyre_fresh,
    position_before_early,
    position_before_late,
    position_after_early,
    position_after_late,
    gap_before_sec,
    gap_after_sec,
    net_time_gain_sec,
    early_stop_duration_sec,
    late_stop_duration_sec,
    stop_duration_delta_sec,
    on_track_gain_sec,
    position_flip,
    window_green,
    eligible,
    exclusion_reason,
    confidence,
    opportunity_type,
    outcome_label,
    methodology_version
from marts.pit_window_effectiveness

-- Evidence 40 cannot serialise a zero-row source. Season zero remains internal
-- and is filtered from every user-facing query.
union all
select
    0, 0, '__NO_DATA__', 'R00 · No data', 0,
    '__NO_DATA__', '__NO_DATA__', '__NO_DATA__',
    '__NO_DATA__', '__NO_DATA__', '__NO_DATA__',
    0, 0, 0, 0, 0,
    '__NO_DATA__', '__NO_DATA__', '__NO_DATA__', '__NO_DATA__',
    false, false,
    0, 0, 0, 0,
    cast(null as double), cast(null as double), cast(null as double),
    cast(null as double), cast(null as double), cast(null as double), cast(null as double),
    false, false, false,
    'No data', 'excluded', 'No opportunity', 'Excluded', 'pit-window-v1'
where not exists (select 1 from marts.pit_window_effectiveness)
order by season, round, early_pit_lap, early_driver_code, late_driver_code
