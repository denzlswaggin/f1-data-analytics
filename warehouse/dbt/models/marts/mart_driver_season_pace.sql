-- Per-driver, per-season teammate pace summary.
--
-- One row per driver per season: how they measured up against their teammate(s)
-- in qualifying that year — head-to-head record and mean pace gap (negative =
-- faster than teammate on average).
with gaps as (
    select * from {{ ref('int_teammate_quali_gaps') }}
),

drivers as (
    select * from {{ ref('stg_drivers') }}
)

select
    gaps.driver_id,
    drivers.driver_name,
    gaps.season,
    count(*)                                                as races_compared,
    sum(case when gaps.beat_teammate then 1 else 0 end)     as teammate_quali_wins,
    100.0 * avg(case when gaps.beat_teammate then 1.0 else 0.0 end)
        as teammate_win_pct,
    avg(gaps.pace_gap)                                      as mean_pace_gap,
    stddev_samp(gaps.pace_gap)                              as stddev_pace_gap
from gaps
left join drivers on gaps.driver_id = drivers.driver_id
group by gaps.driver_id, drivers.driver_name, gaps.season
