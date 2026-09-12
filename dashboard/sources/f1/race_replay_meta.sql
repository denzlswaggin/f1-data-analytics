-- Tiny per-driver lookup for the replay: display name, team, and livery colour.
-- One row per car per race (a couple of dozen rows), joined to the big replay
-- feed client-side by driver_code so colours/labels don't bloat that feed.
with drivers as (
    -- Python materialises an empty replay with inferred pandas dtypes. DuckDB can
    -- therefore see driver_code as INTEGER until real replay rows are available.
    -- Normalise it here so the metadata source also works for an empty replay.
    select distinct season, round, cast(driver_code as varchar) as driver_code
    from marts.race_replay
),

team as (
    select
        season,
        round,
        cast(driver_code as varchar) as driver_code,
        max(team) as team
    from staging.stg_laps
    where session = 'R'
    group by season, round, driver_code
)

select
    d.season,
    d.round,
    cast(d.season as varchar) || ' ' || rc.race_name as race_name,
    d.driver_code,
    coalesce(dc.driver_name, d.driver_code) as driver_name,
    t.team,
    coalesce(cc.team_color, '#9aa0a6')      as team_color,
    results.grid_position,
    results.finish_position,
    results.status,
    results.is_classified
from drivers d
left join team t
    on t.season = d.season and t.round = d.round and t.driver_code = d.driver_code
left join staging.stg_driver_codes dc
    on dc.season = d.season and dc.driver_code = d.driver_code
left join staging.constructor_colors cc
    on cc.team = t.team
left join staging.stg_results results
    on results.season = d.season
    and results.round = d.round
    and results.driver_code = d.driver_code
left join staging.stg_races rc
    on rc.season = d.season and rc.round = d.round

-- Prevent Evidence from emitting an invalid empty Parquet before replay data exists.
union all
select
    0,
    0,
    '__NO_DATA__',
    '__NO_DATA__',
    'Replay unavailable',
    null,
    '#9aa0a6',
    null,
    null,
    null,
    null
where not exists (select 1 from drivers)
