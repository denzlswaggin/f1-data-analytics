{#
    Use the custom schema name as-is (staging / intermediate / marts) rather than
    dbt's default of prefixing it with the target schema. This keeps warehouse
    schema names identical and predictable across the DuckDB (dev) and Postgres
    (prod) targets.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
