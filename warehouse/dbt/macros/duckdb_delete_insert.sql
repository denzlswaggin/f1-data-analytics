{#
  dbt-duckdb's list-key delete+insert joins every source row to every target
  row sharing the key. A partition key such as (season, round) therefore turns
  a 242k-row race refresh into a many-to-many join. Deduplicating the tiny key
  relation preserves delete+insert semantics and makes cost depend on the number
  of touched partitions rather than the Cartesian number of telemetry rows.
#}
{% macro duckdb__get_delete_insert_merge_sql(
    target, source, unique_key, dest_columns, incremental_predicates
) -%}
    {%- set dest_cols_csv = get_quoted_csv(dest_columns | map(attribute="name")) -%}

    {% if unique_key %}
        {% if unique_key is sequence and unique_key is not string %}
            delete from {{ target }} as DBT_INCREMENTAL_TARGET
            using (
                select distinct
                    {% for key in unique_key %}{{ key }}{{ "," if not loop.last }}{% endfor %}
                from {{ source }}
            ) as DBT_INCREMENTAL_KEYS
            where
                {% for key in unique_key %}
                    DBT_INCREMENTAL_KEYS.{{ key }} = DBT_INCREMENTAL_TARGET.{{ key }}
                    {{ "and" if not loop.last }}
                {% endfor %}
                {% if incremental_predicates %}
                    {% for predicate in incremental_predicates %}
                        and {{ predicate }}
                    {% endfor %}
                {% endif %};
        {% else %}
            delete from {{ target }}
            where ({{ unique_key }}) in (
                select distinct {{ unique_key }} from {{ source }}
            )
            {% if incremental_predicates %}
                {% for predicate in incremental_predicates %}
                    and {{ predicate }}
                {% endfor %}
            {% endif %};
        {% endif %}
    {% endif %}

    insert into {{ target }} ({{ dest_cols_csv }})
    (
        select {{ dest_cols_csv }} from {{ source }}
    )
{%- endmacro %}
