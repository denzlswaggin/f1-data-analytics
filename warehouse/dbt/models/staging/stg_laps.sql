-- One clean, typed row per driver per lap (FastF1). Covers 2024-2026; used for race
-- pace and tyre-stint analysis. Driver key here is the 3-letter code (FastF1),
-- not the Ergast driver_id.
with source as (
    select * from {{ source('raw', 'laps') }}
    where {{ season_in_context('season') }}
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
        case
            when compound is null or lower(trim(compound)) in ('', 'none', 'nan') then 'UNKNOWN'
            else upper(trim(compound))
        end                                                as compound,
        cast(tyre_life as integer)                          as tyre_life,
        is_fresh_tyre,
        cast(position as integer)                           as position,
        is_personal_best,
        track_status,
        cast(lap_start_sec as double precision)             as lap_start_sec,
        {{ optional_source_column(source('raw', 'laps'), 'pit_in_time_sec', 'double precision') }}
                                                           as pit_in_time_sec,
        {{ optional_source_column(source('raw', 'laps'), 'pit_out_time_sec', 'double precision') }}
                                                           as pit_out_time_sec,
        cast(speed_i1_kph as double precision)              as speed_i1_kph,
        cast(speed_i2_kph as double precision)              as speed_i2_kph,
        cast(speed_fl_kph as double precision)              as speed_fl_kph,
        cast(speed_st_kph as double precision)              as speed_st_kph,
        lap_time_sec,
        sector1_sec,
        sector2_sec,
        sector3_sec
    from source
)

select * from renamed
