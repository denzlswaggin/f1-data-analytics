-- Compatibility result table. Pace belongs to the separately validated serving
-- analysis; dbt must not recreate the retired pit-contaminated mean model.
with scopes as (
    select distinct season, round from {{ ref('mart_lap_times') }}
), stops as (
    select season, round, driver_id, count(*) as stops
    from {{ ref('stg_pitstops') }} group by season, round, driver_id
), stop_coverage as (
    select distinct season, round from {{ ref('stg_pitstops') }}
)
select
    results.season,
    results.round,
    races.race_name,
    results.driver_code,
    results.driver_id,
    results.driver_name,
    results.constructor_id as team,
    cast(0 as bigint) as pace_samples,
    cast(null as double precision) as controlled_pace_delta_sec,
    results.grid_position,
    results.finish_position,
    results.status,
    cast(null as integer) as pace_rank,
    results.is_classified,
    case when stop_coverage.season is not null then coalesce(stops.stops, 0) end as stops,
    case when results.grid_position > 0
        then results.grid_position - results.finish_position end as grid_gain,
    cast(null as integer) as outcome_vs_pace,
    'Recorded result; pace supplied by separate analysis' as story_label,
    'recorded-results-v1' as methodology_version
from {{ ref('stg_results') }} as results
inner join scopes on results.season = scopes.season and results.round = scopes.round
inner join {{ ref('stg_races') }} as races
    on results.season = races.season and results.round = races.round
left join stops on results.season = stops.season and results.round = stops.round
    and results.driver_id = stops.driver_id
left join stop_coverage on results.season = stop_coverage.season
    and results.round = stop_coverage.round
