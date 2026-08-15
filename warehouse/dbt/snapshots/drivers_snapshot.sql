{% snapshot drivers_snapshot %}
{{
    config(
        target_schema='snapshots',
        unique_key='driver_id',
        strategy='check',
        check_cols=['driver_name', 'last_season', 'race_entries'],
    )
}}
-- Slowly-changing dimension: as the current season progresses, drivers' last
-- season and race_entries change. The snapshot records each change over time
-- (dbt_valid_from / dbt_valid_to), so history is preserved across pipeline runs.
select
    driver_id,
    driver_name,
    nationality,
    first_season,
    last_season,
    race_entries
from {{ ref('stg_drivers') }}
{% endsnapshot %}
