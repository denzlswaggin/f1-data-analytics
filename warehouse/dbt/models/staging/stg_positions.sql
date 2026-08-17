-- One clean, typed row per driver per position sample (FastF1 positional feed).
-- Unlike stg_telemetry (distance-gridded, per lap), these carry the shared
-- session clock (session_time_sec) so every car can be placed at the same
-- instant — the basis for the animated race-replay map. Keyed on driver_code
-- (FastF1); bridged to the Ergast driver_id downstream via stg_driver_codes.
with source as (
    select * from {{ source('raw', 'positions') }}
),

renamed as (
    select
        {{ dbt_utils.generate_surrogate_key(
            ['season', 'round', 'session', 'driver_code', 'session_time_sec']
        ) }}                                                as position_key,
        cast(season as integer)                             as season,
        cast(round as integer)                              as round,
        session,
        driver_code,
        cast(session_time_sec as double precision)          as session_time_sec,
        cast(x as double precision)                         as x,
        cast(y as double precision)                         as y,
        status
    from source
)

select * from renamed
