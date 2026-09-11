with completed as (
    select distinct season, round from staging.stg_results
    where season between 2024 and 2026
), stops as (
    select season, round, count(*) as observed_stops,
        count(*) filter (where eligible) as eligible_stops,
        count(distinct driver_code) as drivers
    from marts.pit_timing_sensitivity group by season, round
), laps as (
    select season, round, count(*) as lap_rows
    from staging.stg_laps where session = 'R' group by season, round
), replay as (
    select season, round, count(*) as replay_rows
    from marts.race_replay group by season, round
)
select completed.season, completed.round, races.race_name, races.race_date,
    coalesce(stops.observed_stops, 0) as observed_stops,
    coalesce(stops.eligible_stops, 0) as eligible_stops,
    coalesce(stops.drivers, 0) as drivers,
    coalesce(laps.lap_rows, 0) as lap_rows,
    coalesce(replay.replay_rows, 0) as replay_rows
from completed
join staging.stg_races as races using (season, round)
left join stops using (season, round)
left join laps using (season, round)
left join replay using (season, round)
order by season, round
