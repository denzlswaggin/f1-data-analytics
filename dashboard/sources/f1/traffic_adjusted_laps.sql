select
    season,
    round,
    race_name,
    driver_code,
    team,
    lap_number,
    stint,
    compound,
    tyre_life,
    lap_time_sec,
    context_samples,
    valid_context_samples,
    traffic_samples,
    traffic_share,
    clean_air_share,
    replay_coverage_pct,
    median_gap_to_ahead_s,
    air_state,
    peer_lap_avg_sec,
    peer_lap_median_sec,
    peer_count,
    controlled_pace_delta_sec,
    matched_clean_laps,
    matched_clean_delta_sec,
    paired_traffic_delta_sec
from marts.traffic_adjusted_laps

-- Typed sentinel for Evidence's empty-source Parquet edge case; page filters
-- exclude season zero from every user-visible query.
union all
select
    0, 0, '__NO_DATA__', '__NO_DATA__', '__NO_DATA__',
    0, 0, '__NO_DATA__', cast(0 as double), cast(0 as double),
    0, 0, 0, cast(0 as double), cast(0 as double), cast(0 as double),
    cast(null as double), 'mixed', cast(null as double), cast(null as double),
    cast(0 as bigint), cast(null as double),
    0, cast(null as double), cast(null as double)
where not exists (select 1 from marts.traffic_adjusted_laps)
order by season, round, driver_code, lap_number
