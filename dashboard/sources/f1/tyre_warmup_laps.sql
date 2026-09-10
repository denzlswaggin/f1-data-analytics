select
    season,
    round,
    race_name,
    driver_code,
    driver_name,
    team,
    stint,
    compound,
    is_fresh_tyre,
    out_lap,
    lap_number,
    post_stop_offset,
    tyre_life,
    lap_time_sec,
    track_status,
    air_state,
    replay_coverage_pct,
    traffic_share,
    median_gap_to_ahead_s,
    controlled_pace_delta_sec,
    expected_mature_delta_sec,
    warmup_loss_sec,
    used_for_baseline,
    within_stable_band,
    lap_eligible,
    lap_exclusion_reason,
    methodology_version
from marts.tyre_warmup_laps

union all
select
    0, 0, '__NO_DATA__', '__NO_DATA__', '__NO_DATA__', '__NO_DATA__',
    0, '__NO_DATA__', false, 0, 0, 0, cast(null as double), cast(null as double),
    '__NO_DATA__', 'unavailable', cast(null as double), cast(null as double),
    cast(null as double), cast(null as double), cast(null as double), cast(null as double),
    false, false, false, 'No data', 'tyre-warmup-v3-observation'
where not exists (select 1 from marts.tyre_warmup_laps)
order by season, round, driver_code, stint, lap_number
