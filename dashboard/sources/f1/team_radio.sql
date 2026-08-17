-- Team-radio clips aligned to the replay clock: t_s = seconds since the green
-- light, restricted to the race window (grid/cool-down radio is dropped). Audio
-- only — recording_url is the MP3. Coverage is partial (OpenF1).
with win as (
    select
        season,
        round,
        min(lap_start_sec) as t0,
        max(lap_start_sec + coalesce(lap_time_sec, 0)) as t1
    from staging.stg_laps
    where session = 'R'
    group by season, round
)

select
    r.season,
    r.round,
    rc.race_name,
    round(r.session_time_sec - w.t0, 1) as t_s,
    r.driver_code,
    r.recording_url
from staging.stg_team_radio r
join win w
    on w.season = r.season and w.round = r.round
left join staging.stg_races rc
    on rc.season = r.season and rc.round = r.round
where r.session = 'R'
    and r.session_time_sec - w.t0 between 0 and (w.t1 - w.t0)
order by rc.race_name, t_s
