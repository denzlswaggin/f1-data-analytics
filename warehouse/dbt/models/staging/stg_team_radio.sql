-- One clean, typed row per team-radio clip (OpenF1), on the shared session clock
-- (session_time_sec). Audio only — recording_url points to the MP3. Coverage is
-- partial (OpenF1 doesn't have radio for every race yet).
with source as (
    select * from {{ source('raw', 'team_radio') }}
),

renamed as (
    select
        {{ dbt_utils.generate_surrogate_key(
            ['season', 'round', 'session', 'recording_url']
        ) }}                                                as radio_key,
        cast(season as integer)                             as season,
        cast(round as integer)                              as round,
        session,
        cast(session_time_sec as double precision)          as session_time_sec,
        driver_number,
        driver_code,
        recording_url
    from source
)

select * from renamed
