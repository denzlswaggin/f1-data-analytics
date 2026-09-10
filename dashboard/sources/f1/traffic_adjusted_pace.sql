select
    season,
    round,
    race_name,
    'R' || lpad(cast(round as varchar), 2, '0') || ' · '
        || replace(race_name, ' Grand Prix', '') as race_label,
    driver_code,
    team,
    eligible_laps,
    clean_air_laps,
    traffic_laps,
    mixed_laps,
    matched_traffic_laps,
    traffic_exposure_pct,
    replay_coverage_pct,
    observed_controlled_pace_delta_sec,
    clean_air_controlled_pace_delta_sec,
    traffic_adjusted_pace_delta_sec,
    traffic_controlled_pace_delta_sec,
    traffic_associated_delta_sec_per_lap,
    traffic_associated_p25_sec,
    traffic_associated_p75_sec,
    confidence,
    clean_air_eligible,
    clean_air_confidence,
    traffic_association_eligible,
    traffic_association_confidence,
    traffic_gap_threshold_s,
    clean_air_gap_threshold_s,
    methodology_version
from marts.traffic_adjusted_pace

-- Evidence 40 emits an invalid zero-byte Parquet for an empty source. Keep one
-- internal sentinel until the optional Python mart has been materialised.
union all
select
    0, 0, '__NO_DATA__', 'R00 · No data', '__NO_DATA__', '__NO_DATA__',
    0, 0, 0, 0, 0,
    cast(0 as double), cast(0 as double),
    cast(null as double), cast(null as double), cast(null as double),
    cast(null as double), cast(null as double), cast(null as double), cast(null as double),
    'unavailable', false, 'unavailable', false, 'unavailable',
    cast(1.5 as double), cast(3.0 as double), 'traffic-v3-metric-evidence'
where not exists (select 1 from marts.traffic_adjusted_pace)
order by season, round, driver_code
