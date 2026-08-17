-- Tiny per-driver lookup for the replay: display name, team, and livery colour.
-- One row per car per race (a couple of dozen rows), joined to the big replay
-- feed client-side by driver_code so colours/labels don't bloat that feed.
with drivers as (
    select distinct season, round, driver_code
    from marts.race_replay
),

team as (
    select
        season,
        round,
        driver_code,
        max(team) as team
    from staging.stg_laps
    where session = 'R'
    group by season, round, driver_code
)

select
    d.season,
    d.round,
    cast(d.season as varchar) || ' ' || rc.race_name as race_name,
    d.driver_code,
    coalesce(dc.driver_name, d.driver_code) as driver_name,
    t.team,
    coalesce(cc.team_color, '#9aa0a6')      as team_color
from drivers d
left join team t
    on t.season = d.season and t.round = d.round and t.driver_code = d.driver_code
left join staging.stg_driver_codes dc
    on dc.season = d.season and dc.driver_code = d.driver_code
left join staging.constructor_colors cc
    on cc.team = t.team
left join staging.stg_races rc
    on rc.season = d.season and rc.round = d.round
