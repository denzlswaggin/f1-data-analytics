-- One clean, typed row per weather sample (FastF1, ~per minute) for a session.
-- Feeds the weather-adjusted degradation mart, which summarises to race grain.
with source as (
    select * from {{ source('raw', 'weather') }}
),

renamed as (
    select
        {{ dbt_utils.generate_surrogate_key(
            ['season', 'round', 'session', 'time_sec']
        ) }}                                                as weather_key,
        cast(season as integer)                             as season,
        cast(round as integer)                              as round,
        session,
        cast(time_sec as double precision)                  as time_sec,
        cast(air_temp as double precision)                  as air_temp,
        cast(track_temp as double precision)                as track_temp,
        cast(humidity as double precision)                  as humidity,
        cast(pressure as double precision)                  as pressure,
        cast(wind_speed as double precision)                as wind_speed,
        cast(wind_direction as double precision)            as wind_direction,
        is_raining
    from source
)

select * from renamed
