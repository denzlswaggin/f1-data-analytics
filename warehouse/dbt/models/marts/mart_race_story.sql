-- Insight-first race summary: controlled pace rank versus the actual result.
-- Each lap is compared with the field average on the same race lap and compound,
-- which controls fuel load and compound choice without pretending to be a causal
-- strategy model. At least three cars must share the comparison cell.
with lap_context as (
    select
        *,
        avg(lap_time_sec) over (
            partition by season, round, lap_number, compound
        ) as field_lap_avg_sec,
        count(*) over (
            partition by season, round, lap_number, compound
        ) as field_lap_size
    from {{ ref('mart_lap_times') }}
    where lap_number > 1
        and tyre_life >= 2
        and compound not in ('UNKNOWN', 'None', 'nan')
),

pace as (
    select
        season,
        round,
        max(race_name) as race_name,
        driver_code,
        max(driver_id) as driver_id,
        max(driver_name) as driver_name,
        max(team) as team,
        count(*) as pace_samples,
        avg(lap_time_sec - field_lap_avg_sec) as controlled_pace_delta_sec
    from lap_context
    where field_lap_size >= 3
    group by season, round, driver_code
),

pace_ranked as (
    select
        *,
        rank() over (
            partition by season, round order by controlled_pace_delta_sec
        ) as pace_rank
    from pace
),

stops as (
    select
        season,
        round,
        driver_code,
        count(*) - 1 as stops
    from {{ ref('mart_stint_strategy') }}
    group by season, round, driver_code
),

joined as (
    select
        pace_ranked.season,
        pace_ranked.round,
        pace_ranked.race_name,
        pace_ranked.driver_code,
        pace_ranked.driver_id,
        pace_ranked.driver_name,
        pace_ranked.team,
        results.grid_position,
        results.finish_position,
        results.status,
        case
            when results.is_classified or results.status = 'Lapped' then true
            else false
        end as is_classified,
        pace_ranked.pace_samples,
        pace_ranked.controlled_pace_delta_sec,
        cast(pace_ranked.pace_rank as integer) as pace_rank,
        coalesce(stops.stops, 0) as stops
    from pace_ranked
    inner join {{ ref('stg_results') }} as results
        on results.season = pace_ranked.season
        and results.round = pace_ranked.round
        and results.driver_code = pace_ranked.driver_code
    left join stops
        on stops.season = pace_ranked.season
        and stops.round = pace_ranked.round
        and stops.driver_code = pace_ranked.driver_code
)

select
    *,
    grid_position - finish_position as grid_gain,
    pace_rank - finish_position as outcome_vs_pace,
    case
        when not is_classified then 'Retirement / incident'
        when finish_position = 1 and pace_rank = 1 then 'Pace-supported win'
        when pace_rank - finish_position >= 3 then 'Execution gain'
        when pace_rank - finish_position <= -3 then 'Missed conversion'
        when grid_position - finish_position >= 5 then 'Comeback drive'
        else 'Representative finish'
    end as story_label
from joined
