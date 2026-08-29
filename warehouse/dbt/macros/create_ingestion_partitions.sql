{% macro create_ingestion_partitions() %}
    {% if not var('load_ci_seeds', false) | as_bool %}
    {% set ddl %}
        create schema if not exists raw;
        create table if not exists raw.ingestion_partitions (
            resource varchar,
            season integer,
            round integer,
            session varchar,
            loaded_at timestamp,
            load_id varchar,
            row_count bigint
        )
    {% endset %}
    {% do run_query(ddl) %}
    {% endif %}
{% endmacro %}
