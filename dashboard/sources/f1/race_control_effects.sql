select
    season,
    round,
    race_name,
    event_id,
    event_number,
    event_type,
    driver_code,
    effect_type,
    effect_scope,
    value,
    lower_bound,
    upper_bound,
    unit,
    evidence_class,
    confidence,
    sample_size,
    eligible,
    exclusion_reason,
    methodology_version
from marts.race_control_effects

union all
select
    0, 0, '__NO_DATA__', '__NO_DATA__', 0, 'No event', '__NO_DATA__',
    'unavailable', 'unavailable', cast(null as double), cast(null as double),
    cast(null as double), '', 'unavailable', 'insufficient', 0, false,
    'No data', 'race-control-impact-v3'
where not exists (select 1 from marts.race_control_effects)
order by season, round, event_number, driver_code, effect_type
