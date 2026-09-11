-- Keep completed races selectable even when no neutralisation was recorded.
with completed as (
    select distinct season, round
    from staging.stg_results
    where season between 2024 and 2026
), messages as (
    select season, round, count(*) as message_count
    from staging.stg_race_control
    where session = 'R'
    group by season, round
), events as (
    select season, round, count(*) as event_count,
        count(*) filter (where eligible) as eligible_event_count
    from marts.race_control_events
    group by season, round
)
select completed.season, completed.round, races.race_name, races.race_date,
    coalesce(messages.message_count, 0) as message_count,
    coalesce(events.event_count, 0) as event_count,
    coalesce(events.eligible_event_count, 0) as eligible_event_count
from completed
join staging.stg_races as races using (season, round)
left join messages using (season, round)
left join events using (season, round)
order by season, round
