{% macro season_in_context(column) %}
    cast({{ column }} as integer) between 2024 and 2026
{% endmacro %}
