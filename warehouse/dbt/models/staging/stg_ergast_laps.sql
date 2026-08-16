-- One clean, typed row per driver per lap (Ergast per-lap position and time).
-- Distinct from stg_laps (FastF1): this is keyed on the Ergast driver_id and
-- carries track position, which FastF1 laps also do but for a shorter era.
with source as (
    select * from {{ source('raw', 'ergast_laps') }}
),

renamed as (
    select
        {{ dbt_utils.generate_surrogate_key(
            ['season', 'round', 'driver_id', 'lap']
        ) }}                                                as ergast_lap_key,
        cast(season as integer)                             as season,
        cast(round as integer)                              as round,
        driver_id,
        cast(lap as integer)                                as lap_number,
        cast(position as integer)                           as position,
        {{ parse_laptime('lap_time') }}                     as lap_time_sec
    from source
)

select * from renamed
