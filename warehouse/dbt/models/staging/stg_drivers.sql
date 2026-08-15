-- Driver dimension derived from race results (no dedicated drivers endpoint is
-- ingested yet). One row per driver with a display name and career span.
with results as (
    select * from {{ ref('stg_results') }}
)

select
    driver_id,
    max(driver_code)         as driver_code,
    max(driver_name)         as driver_name,
    max(driver_nationality)  as nationality,
    min(season)              as first_season,
    max(season)              as last_season,
    count(*)                 as race_entries
from results
group by driver_id
