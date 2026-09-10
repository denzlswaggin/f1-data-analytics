select
    season,
    round,
    race_name,
    'R' || lpad(cast(round as varchar), 2, '0') || ' · '
        || replace(race_name, ' Grand Prix', '') as race_label,
    driver_code,
    driver_name,
    team,
    attacking_opportunities,
    converted_opportunities,
    attacks_defended,
    attack_conversion_pct,
    attack_conversion_p05_pct,
    attack_conversion_p95_pct,
    attack_pressure_s,
    distinct_defenders,
    median_time_to_pass_s,
    defensive_opportunities,
    defences_held,
    passes_conceded,
    defence_hold_pct,
    defence_hold_p05_pct,
    defence_hold_p95_pct,
    defensive_pressure_s,
    distinct_attackers,
    interrupted_attacks,
    unresolved_attacks,
    interrupted_defences,
    unresolved_defences,
    quick_reversals_made,
    quick_reversals_conceded,
    longest_battle_s,
    offense_eligible,
    defense_eligible,
    offense_exclusion_reason,
    defense_exclusion_reason,
    offense_confidence,
    defense_confidence,
    confidence,
    methodology_version
from marts.racecraft_driver_summary

union all
select
    0, 0, '__NO_DATA__', 'R00 · No data', '__NO_DATA__', '__NO_DATA__',
    '__NO_DATA__', 0, 0, 0, cast(null as double), cast(null as double),
    cast(null as double), cast(null as double), 0, cast(null as double),
    0, 0, 0, cast(null as double), cast(null as double), cast(null as double),
    cast(null as double), 0, 0, 0, 0, 0, 0, 0, cast(null as double),
    false, false, 'No data', 'No data', 'insufficient', 'insufficient',
    'insufficient', 'racecraft-v3-continuity'
where not exists (select 1 from marts.racecraft_driver_summary)
order by season, round, driver_code
