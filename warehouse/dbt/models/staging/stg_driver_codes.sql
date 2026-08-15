-- Bridge from the FastF1 3-letter driver_code to the Ergast driver_id, at season
-- grain. Telemetry models (stg_laps and the marts on top of it) key on
-- driver_code only; this lets them join the Ergast driver/constructor dimensions.
--
-- Season grain, not global: a 3-letter code is not 1:1 with a driver across all
-- history (e.g. VER = Jos vs Max Verstappen, MAG = Jan vs Kevin Magnussen), but
-- within a single season it is unambiguous. Constructor is deliberately left out
-- here — a driver can switch teams mid-season, so team is a race-grain fact
-- (join stg_results on (season, round, driver_id) where a mart needs it).
with results as (
    select
        season,
        driver_code,
        driver_id,
        driver_name
    from {{ ref('stg_results') }}
    where driver_code is not null
)

select distinct
    season,
    driver_code,
    driver_id,
    driver_name
from results
