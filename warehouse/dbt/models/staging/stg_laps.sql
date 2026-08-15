-- One clean, typed row per driver per lap (FastF1). Covers 2018+; used for race
-- pace and tyre-stint analysis. Driver key here is the 3-letter code (FastF1),
-- not the Ergast driver_id.
with source as (
    select * from {{ source('raw', 'laps') }}
),

renamed as (
    select
        {{ dbt_utils.generate_surrogate_key(
            ['season', 'round', 'session', 'driver_code', 'lap_number']
        ) }}                                                as lap_key,
        cast(season as integer)                             as season,
        cast(round as integer)                              as round,
        session,
        driver_code,
        driver_number,
        team,
        cast(lap_number as integer)                         as lap_number,
        cast(stint as integer)                              as stint,
        compound,
        cast(tyre_life as integer)                          as tyre_life,
        is_fresh_tyre,
        cast(position as integer)                           as position,
        is_personal_best,
        track_status,
        lap_time_sec,
        sector1_sec,
        sector2_sec,
        sector3_sec
    from source
)

select * from renamed
