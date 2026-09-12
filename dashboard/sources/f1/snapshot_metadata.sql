with metadata as (
    select version, generated_at, source, latest_event_date
    from dashboard.snapshot_metadata
),

calendar as (
    select max(race_date) filter (where race_date < current_date) as latest_completed_event_date
    from staging.stg_races
)

select
    metadata.*,
    calendar.latest_completed_event_date,
    date_diff('day', metadata.latest_event_date, calendar.latest_completed_event_date)
        as freshness_lag_days,
    case
        when metadata.latest_event_date is null then 'unknown'
        when calendar.latest_completed_event_date is null then 'unknown'
        when metadata.latest_event_date >= calendar.latest_completed_event_date then 'current'
        else 'stale'
    end as freshness_status
from metadata
cross join calendar
