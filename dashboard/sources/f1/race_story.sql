-- Serving story v2: observed results plus pit-excluded robust peer comparisons.
-- Do not fall back to the legacy mart's contaminated pace or inferred stop count.
with pace as (
    select season, round, driver_code,
        count(*) as pace_samples,
        median(controlled_pace_delta_sec) as controlled_pace_delta_sec
    from marts.traffic_adjusted_laps
    where isfinite(controlled_pace_delta_sec)
    group by season, round, driver_code
), ranked as (
    select *, rank() over (
        partition by season, round order by controlled_pace_delta_sec
    ) as pace_rank
    from pace where pace_samples >= 5
), scopes as (
    select distinct season, round from marts.mart_lap_times
), stops as (
    select season, round, driver_id, count(*) as stops
    from marts.mart_pit_strategy group by season, round, driver_id
), stop_coverage as (
    select distinct season, round from marts.mart_pit_strategy
), pass_coverage as (
    select season, round from marts.racecraft_processing
    group by season, round having count(*) = 1
), order_coverage as (
    select distinct season, round, driver_code from marts.race_replay
    where running_order > 0 and isfinite(t_s)
), made as (
    select season, round, passer_code as driver_code, count(*) as passes_made
    from marts.race_overtakes group by season, round, passer_code
), lost as (
    select season, round, passed_code as driver_code, count(*) as passes_lost
    from marts.race_overtakes group by season, round, passed_code
), joined as (
    select results.season, results.round, races.race_name,
        results.driver_code, results.driver_id, results.driver_name,
        results.constructor_id as team,
        coalesce(pace.pace_samples, 0) as pace_samples,
        ranked.controlled_pace_delta_sec, ranked.pace_rank,
        results.grid_position, results.finish_position, results.status,
        results.is_classified,
        case when stop_coverage.season is not null then coalesce(stops.stops, 0) end as stops,
        case when results.grid_position > 0 then results.grid_position - results.finish_position end as grid_gain,
        count(ranked.pace_rank) over (partition by results.season, results.round)
            = count(*) over (partition by results.season, results.round) as pace_field_complete,
        case when count(ranked.pace_rank) over (partition by results.season, results.round)
            = count(*) over (partition by results.season, results.round)
            then ranked.pace_rank - results.finish_position end as outcome_vs_pace,
        cast(results.season as varchar) || ' ' || races.race_name as race_label,
        case when pass_coverage.season is not null and order_coverage.driver_code is not null then coalesce(made.passes_made, 0) end as passes_made,
        case when pass_coverage.season is not null and order_coverage.driver_code is not null then coalesce(lost.passes_lost, 0) end as passes_lost,
        case when pass_coverage.season is not null and order_coverage.driver_code is not null then 'Model processed; event accuracy unverified'
            else 'Pass analysis unavailable' end as pass_evidence,
        'race-story-v2-robust-peers' as methodology_version
    from staging.stg_results as results
    join scopes using (season, round)
    join staging.stg_races as races using (season, round)
    left join pace using (season, round, driver_code)
    left join ranked using (season, round, driver_code)
    left join stops using (season, round, driver_id)
    left join stop_coverage using (season, round)
    left join pass_coverage using (season, round)
    left join order_coverage using (season, round, driver_code)
    left join made using (season, round, driver_code)
    left join lost using (season, round, driver_code)
)
select *, passes_made - passes_lost as net_on_track_passes,
    case when pace_rank is null then 'Insufficient comparable pace laps'
        when not pace_field_complete then 'Pace rank covers eligible drivers only'
        when outcome_vs_pace > 0 then 'Finish ahead of model rank'
        when outcome_vs_pace < 0 then 'Finish behind model rank'
        else 'Finish matches model rank' end as story_label
from joined
order by season desc, round desc, finish_position
