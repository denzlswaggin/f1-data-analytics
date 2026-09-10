{% macro optional_source_column(relation, column_name, sql_type) %}
    {# Historical raw partitions and CI seeds may predate additive fields. #}
    {% set names = [] %}
    {% if execute %}
        {% for column in adapter.get_columns_in_relation(relation) %}
            {% do names.append(column.name | lower) %}
        {% endfor %}
    {% endif %}
    {% if column_name | lower in names %}
        cast({{ adapter.quote(column_name) }} as {{ sql_type }})
    {% else %}
        cast(null as {{ sql_type }})
    {% endif %}
{% endmacro %}
