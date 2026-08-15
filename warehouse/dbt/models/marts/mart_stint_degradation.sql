-- Per-driver-stint tyre degradation: a linear fit of lap time vs tyre age within
-- each individual stint (season, round, driver, stint), rather than the pooled
-- per-race/compound estimate in mart_tyre_degradation. The slope is the pace lost
-- per lap of tyre life (sec/lap; higher = the stint "fell off" faster).
--
-- Out-laps (tyre_life < 2) are excluded; a stint needs >= 5 clean green-flag laps
-- for a stable slope (tighter than the pooled mart's >= 8, since a single stint
-- has far fewer laps than a whole race). driver_id / driver_name come bridged
-- through mart_lap_times (see stg_driver_codes).
with laps as (
    select * from {{ ref('mart_lap_times') }}
    where tyre_life >= 2 and compound is not null
)

select
    season,
    round,
    race_name,
    driver_code,
    driver_id,
    driver_name,
    stint,
    max(compound)                        as compound,
    count(*)                             as n_laps,
    max(tyre_life)                       as stint_length,
    regr_slope(lap_time_sec, tyre_life)  as deg_sec_per_lap,
    min(lap_time_sec)                    as best_lap_sec,
    avg(lap_time_sec)                    as avg_lap_sec
from laps
group by season, round, race_name, driver_code, driver_id, driver_name, stint
having count(*) >= 5
