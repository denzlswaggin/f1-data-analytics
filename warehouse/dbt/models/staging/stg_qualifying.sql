-- One clean row per driver per qualifying session, with each of Q1/Q2/Q3
-- parsed into seconds. Qualifying is single-lap pace and is the basis for the
-- teammate-normalised driver rating.
with source as (
    select * from {{ source('raw', 'qualifying') }}
),

parsed as (
    select
        {{ dbt_utils.generate_surrogate_key(['season', 'round', 'driver_id']) }} as qualifying_key,
        {{ dbt_utils.generate_surrogate_key(['season', 'round']) }}              as race_key,
        cast(season as integer)                                                  as season,
        cast(round as integer)                                                   as round,
        driver_id,
        driver_code,
        constructor_id,
        cast(position as integer)                                                as qualifying_position,
        {{ parse_laptime('q1') }}                                                as q1_sec,
        {{ parse_laptime('q2') }}                                                as q2_sec,
        {{ parse_laptime('q3') }}                                                as q3_sec
    from source
)

select * from parsed
