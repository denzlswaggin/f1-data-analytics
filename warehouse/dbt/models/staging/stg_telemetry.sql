-- One clean, typed row per driver per lap per distance point (FastF1 telemetry,
-- resampled onto a uniform distance grid during ingestion). Keyed on driver_code
-- (FastF1); bridged to the Ergast driver_id downstream via stg_driver_codes.
with source as (
    select * from {{ source('raw', 'telemetry') }}
),

renamed as (
    select
        {{ dbt_utils.generate_surrogate_key(
            ['season', 'round', 'session', 'driver_code', 'lap_number', 'distance_m']
        ) }}                                                as telemetry_key,
        cast(season as integer)                             as season,
        cast(round as integer)                              as round,
        session,
        driver_code,
        cast(lap_number as integer)                         as lap_number,
        cast(distance_m as double precision)                as distance_m,
        cast(speed_kph as double precision)                 as speed_kph,
        cast(throttle as double precision)                  as throttle,
        cast(rpm as double precision)                       as rpm,
        cast(x as double precision)                         as x,
        cast(y as double precision)                         as y,
        cast(brake as integer)                              as brake,
        cast(drs as integer)                                as drs,
        cast(gear as integer)                               as gear
    from source
)

select * from renamed
