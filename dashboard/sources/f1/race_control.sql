-- Official race-control messages aligned to the replay clock: t_s = seconds since
-- the green light (session_time_sec minus the race's first lap start), matching the
-- race_replay feed. Flags, safety car, penalties, incidents, DRS.
with win as (
    select
        season,
        round,
        min(lap_start_sec) as t0
    from staging.stg_laps
    where session = 'R'
    group by season, round
)

select
    m.season,
    m.round,
    cast(m.season as varchar) || ' ' || rc.race_name as race_name,
    round(m.session_time_sec - w.t0, 1) as t_s,
    m.category,
    m.flag,
    m.scope,
    m.message,
    m.driver_code
from staging.stg_race_control m
join win w
    on w.season = m.season and w.round = m.round
left join staging.stg_races rc
    on rc.season = m.season and rc.round = m.round
where m.session = 'R'
    and m.session_time_sec - w.t0 >= -10
order by rc.race_name, t_s
