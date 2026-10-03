-- One clean, typed row per pit stop (Ergast). The stop duration string
-- ("22.343" or "1:05.201") is parsed to seconds via the parse_laptime macro.
with source as (
    select * from {{ source('raw', 'pitstops') }}
    where {{ season_in_context('season') }}
),

renamed as (
    select
        {{ dbt_utils.generate_surrogate_key(
            ['season', 'round', 'driver_id', 'stop']
        ) }}                                                as pitstop_key,
        cast(season as integer)                             as season,
        cast(round as integer)                              as round,
        driver_id,
        cast(stop as integer)                               as stop_number,
        cast(lap as integer)                                as pit_lap,
        time_of_day,
        {{ parse_laptime('duration') }}                     as duration_sec
    from source
)

select * from renamed
