with made as (
    select season, round, passer_code as driver_code, count(*) as passes_made
    from marts.race_overtakes
    group by season, round, passer_code
),

lost as (
    select season, round, passed_code as driver_code, count(*) as passes_lost
    from marts.race_overtakes
    group by season, round, passed_code
)

select
    story.*,
    cast(story.season as varchar) || ' ' || story.race_name as race_label,
    coalesce(made.passes_made, 0) as passes_made,
    coalesce(lost.passes_lost, 0) as passes_lost,
    coalesce(made.passes_made, 0) - coalesce(lost.passes_lost, 0) as net_on_track_passes
from marts.mart_race_story as story
left join made using (season, round, driver_code)
left join lost using (season, round, driver_code)
order by season desc, round desc, finish_position
