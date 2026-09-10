select
    season, round, driver_code, lap_number,
    is_pit_in_lap, is_pit_out_lap, is_pit_boundary,
    pit_context_source, pit_context_status, pit_exclusion_reason
from marts.pit_lap_context
union all
select 0, 0, '__NO_DATA__', 0, false, false, false,
    'unavailable', 'unknown', ''
where not exists (select 1 from marts.pit_lap_context)
order by season, round, driver_code, lap_number
