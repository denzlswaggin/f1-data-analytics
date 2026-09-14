-- A successful dbt refresh must not restore unsupported analytical claims.
select * from {{ ref('mart_race_story') }}
where controlled_pace_delta_sec is not null
    or pace_rank is not null
    or outcome_vs_pace is not null
    or pace_samples is distinct from 0
