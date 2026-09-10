with stops as (
    select
        *,
        median(duration_sec) over (partition by season, round) as race_median_stop_sec
    from marts.mart_pit_strategy
),

event_context as (
    select
        stops.season,
        stops.round,
        stops.driver_id,
        stops.stop_number,
        max(
            case
                when upper(coalesce(control.category, '')) = 'SAFETYCAR'
                    or upper(coalesce(control.message, '')) like '%SAFETY CAR%'
                    or upper(coalesce(control.message, '')) like '%VSC%'
                    or upper(coalesce(control.message, '')) like '%RED FLAG%'
                    then 1
                else 0
            end
        ) as intervention_nearby
    from stops
    left join staging.stg_race_control as control
        on control.season = stops.season
        and control.round = stops.round
        and control.session = 'R'
        and control.lap between stops.pit_lap - 2 and stops.pit_lap + 2
    group by stops.season, stops.round, stops.driver_id, stops.stop_number
)

select
    stops.season,
    stops.round,
    stops.race_name,
    cast(stops.season as varchar) || ' ' || stops.race_name as race_label,
    stops.driver_id,
    stops.driver_name,
    stops.stop_number,
    stops.pit_lap,
    stops.duration_sec,
    stops.duration_sec - stops.race_median_stop_sec as stop_delta_sec,
    stops.position_before,
    stops.position_after,
    stops.positions_gained,
    coalesce(event_context.intervention_nearby, 0) = 1 as intervention_nearby,
    case
        when coalesce(event_context.intervention_nearby, 0) = 1 then 'Race-control message nearby'
        when stops.positions_gained is null then 'Insufficient window'
        when stops.positions_gained > 0 then 'Positive cycle'
        when stops.positions_gained < 0 then 'Negative cycle'
        else 'Position held'
    end as impact_label
from stops
left join event_context
    on event_context.season = stops.season
    and event_context.round = stops.round
    and event_context.driver_id = stops.driver_id
    and event_context.stop_number = stops.stop_number
order by stops.season desc, stops.round desc, stops.pit_lap
