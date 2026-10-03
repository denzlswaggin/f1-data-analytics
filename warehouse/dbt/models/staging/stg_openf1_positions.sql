with source as (
    select * from {{ source('raw', 'openf1_positions') }}
    where {{ season_in_context('season') }}
)

select
    {{ dbt_utils.generate_surrogate_key(
        ['season', 'round', 'session', 'driver_number', 'session_time_sec']
    ) }} as openf1_position_key,
    cast(season as integer) as season,
    cast(round as integer) as round,
    session,
    cast(session_key as bigint) as session_key,
    cast(meeting_key as bigint) as meeting_key,
    cast(session_time_sec as double precision) as session_time_sec,
    source_utc,
    driver_number,
    driver_code,
    cast(position as integer) as position,
    source_sha256
from source
where driver_code is not null and position > 0
