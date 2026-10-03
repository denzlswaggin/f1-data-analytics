with source as (
    select * from {{ source('raw', 'openf1_race_control') }}
    where {{ season_in_context('season') }}
)

select
    {{ dbt_utils.generate_surrogate_key(
        ['season', 'round', 'session', 'session_time_sec', 'category', 'message']
    ) }} as openf1_control_key,
    cast(season as integer) as season,
    cast(round as integer) as round,
    session,
    cast(session_key as bigint) as session_key,
    cast(meeting_key as bigint) as meeting_key,
    cast(session_time_sec as double precision) as session_time_sec,
    source_utc,
    category,
    flag,
    message,
    cast(lap_number as integer) as lap_number,
    source_sha256
from source
