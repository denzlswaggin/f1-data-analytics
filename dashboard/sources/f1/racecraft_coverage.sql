with laps as (
    select season, round, count(*) as race_laps,
        count(*) filter (where track_status = '1') as green_laps
    from staging.stg_laps where session = 'R' group by season, round
), replay as (
    select season, round, count(*) as replay_samples,
        count(distinct driver_code) as replay_drivers,
        count(distinct driver_code) filter (where running_order is not null
            and t_s is not null and isfinite(t_s)) as analysable_drivers
    from marts.race_replay group by season, round
), summaries as (
    select season, round, count(distinct driver_code) as analysed_drivers
    from marts.racecraft_driver_summary group by season, round
), processing as (
    select season, round, count(*) as receipts, max(processed_at) as processed_at,
        max(overtake_rows) as detected_passes
    from marts.racecraft_processing group by season, round
), episodes as (
    select season, round, count(*) as observed_battles
    from marts.racecraft_battles group by season, round
), scopes as (
    select season, round from laps union select season, round from replay
)
select s.season, s.round, r.race_name,
    coalesce(p.replay_drivers, 0) as replay_drivers,
    coalesce(p.analysable_drivers, 0) as analysable_drivers,
    coalesce(p.replay_drivers - p.analysable_drivers, 0) as drivers_without_running_order,
    coalesce(a.analysed_drivers, 0) as analysed_drivers,
    coalesce(e.observed_battles, 0) as observed_battles,
    q.processed_at,
    q.detected_passes,
    case when p.replay_samples is null then 'No replay available'
        when coalesce(q.receipts, 0) != 1 then 'Unverified processing: rebuild required'
        when l.race_laps is null then 'Missing race lap context'
        when p.analysable_drivers = 0 then 'No usable running order'
        when a.analysed_drivers is null or a.analysed_drivers < p.analysable_drivers
            then 'Incomplete racecraft processing'
        when l.green_laps = 0 then 'No green-flag lap context'
        when coalesce(e.observed_battles, 0) = 0 then 'Processed: no observed battles'
        else 'Processed' end as coverage_status
from scopes s
left join laps l using (season, round)
left join replay p using (season, round)
left join summaries a using (season, round)
left join episodes e using (season, round)
left join processing q using (season, round)
left join staging.stg_races r using (season, round)
order by s.season, s.round
