-- Tyre degradation segmented by race-day weather.
--
-- Summarises the per-minute weather to a race-grain bucket (wet / hot / cool),
-- then fits lap time vs tyre age (regr_slope) over green-flag laps within each
-- race + compound. Surfaces how fall-off shifts with track temperature and rain.
-- FastF1-sourced (2018+); mirrors mart_tyre_degradation with a weather join.
with race_weather as (
    select
        season,
        round,
        avg(track_temp)                                     as avg_track_temp,
        avg(air_temp)                                       as avg_air_temp,
        max(case when is_raining then 1 else 0 end)         as any_rain
    from {{ ref('stg_weather') }}
    where session = 'R'
    group by season, round
),

bucketed as (
    select
        season,
        round,
        avg_track_temp,
        avg_air_temp,
        case
            when any_rain = 1 then 'wet'
            when avg_track_temp >= 40 then 'hot'
            else 'cool'
        end                                                 as weather_bucket
    from race_weather
),

laps as (
    select * from {{ ref('mart_lap_times') }}
    where tyre_life >= 2 and compound is not null
)

select
    laps.season,
    laps.round,
    laps.race_name,
    laps.compound,
    bucketed.weather_bucket,
    bucketed.avg_track_temp,
    bucketed.avg_air_temp,
    count(*)                                                as n_laps,
    regr_slope(laps.lap_time_sec, laps.tyre_life)           as deg_sec_per_lap,
    avg(laps.lap_time_sec)                                  as avg_lap_sec
from laps
left join bucketed
    on bucketed.season = laps.season
    and bucketed.round = laps.round
group by
    laps.season,
    laps.round,
    laps.race_name,
    laps.compound,
    bucketed.weather_bucket,
    bucketed.avg_track_temp,
    bucketed.avg_air_temp
having count(*) >= 8
