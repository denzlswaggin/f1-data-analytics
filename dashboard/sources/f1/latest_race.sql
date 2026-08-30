with latest as (
    select season, round, race_name
    from marts.mart_lap_times
    group by season, round, race_name
    order by season desc, round desc
    limit 1
),

laps as (
    select
        season,
        round,
        count(*) as lap_rows,
        count(distinct driver_code) as drivers,
        min_by(driver_code, lap_time_sec) as fastest_driver,
        min(lap_time_sec) as fastest_lap_sec
    from marts.mart_lap_times
    group by season, round
),

stints as (
    select season, round, count(*) as stints, count(distinct compound) as compounds
    from marts.mart_stint_strategy
    group by season, round
),

replay as (
    select season, round, count(*) as replay_ticks, max(t_s) - min(t_s) as replay_duration_sec
    from marts.race_replay
    group by season, round
),

passes as (
    select season, round, count(*) as overtakes
    from marts.race_overtakes
    group by season, round
),

weather as (
    select
        season,
        round,
        round(avg(avg_air_temp), 1) as air_temp,
        round(avg(avg_track_temp), 1) as track_temp
    from marts.mart_weather_degradation
    group by season, round
)

select
    latest.season,
    latest.round,
    latest.race_name,
    cast(latest.season as varchar) || ' ' || latest.race_name as race_label,
    laps.lap_rows,
    laps.drivers,
    laps.fastest_driver,
    laps.fastest_lap_sec,
    coalesce(stints.stints, 0) as stints,
    coalesce(stints.compounds, 0) as compounds,
    coalesce(replay.replay_ticks, 0) as replay_ticks,
    coalesce(replay.replay_duration_sec, 0) as replay_duration_sec,
    coalesce(passes.overtakes, 0) as overtakes,
    weather.air_temp,
    weather.track_temp
from latest
join laps using (season, round)
left join stints using (season, round)
left join replay using (season, round)
left join passes using (season, round)
left join weather using (season, round)
