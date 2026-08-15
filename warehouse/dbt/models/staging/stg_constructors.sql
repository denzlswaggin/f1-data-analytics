-- Constructor (team) dimension derived from race results. A proper constructors
-- endpoint with full names can replace this in a later milestone.
with results as (
    select * from {{ ref('stg_results') }}
)

select
    constructor_id,
    min(season)                  as first_season,
    max(season)                  as last_season,
    count(distinct season)       as seasons_active,
    count(*)                     as race_entries
from results
group by constructor_id
