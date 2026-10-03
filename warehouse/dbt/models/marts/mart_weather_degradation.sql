-- Weather observations inside each green lap, on the shared session clock.
-- Missing observations remain unknown; rain elsewhere in the session is irrelevant.
with laps as (
    select pace.*, timing.lap_start_sec
    from {{ ref('mart_lap_times') }} as pace
    inner join {{ ref('stg_laps') }} as timing
        on timing.season = pace.season and timing.round = pace.round
        and timing.driver_code = pace.driver_code and timing.lap_number = pace.lap_number
        and timing.session = 'R'
    where pace.tyre_life >= 2 and pace.compound is not null
),

aligned as (
    select laps.season, laps.round, laps.race_name, laps.driver_code, laps.lap_number,
        laps.compound, laps.tyre_life, laps.lap_time_sec,
        avg(weather.track_temp) as track_temp, avg(weather.air_temp) as air_temp,
        case when count(weather.time_sec) = 0 then null
             when max(case when weather.is_raining then 1 else 0 end) = 1 then 'wet'
             when avg(weather.track_temp) >= 40 then 'hot'
             when avg(weather.track_temp) is not null then 'cool' end as weather_bucket
    from laps
    left join {{ ref('stg_weather') }} as weather
        on weather.season = laps.season and weather.round = laps.round and weather.session = 'R'
        and weather.time_sec >= laps.lap_start_sec
        and weather.time_sec < laps.lap_start_sec + laps.lap_time_sec
    group by laps.season, laps.round, laps.race_name, laps.driver_code, laps.lap_number,
        laps.compound, laps.tyre_life, laps.lap_time_sec
)

select season, round, race_name, compound, weather_bucket,
    avg(track_temp) as avg_track_temp, avg(air_temp) as avg_air_temp,
    count(*) as n_laps, regr_slope(lap_time_sec, tyre_life) as deg_sec_per_lap,
    avg(lap_time_sec) as avg_lap_sec
from aligned
group by season, round, race_name, compound, weather_bucket
having count(*) >= 8
