{#
    Parse an F1 lap-time string into total seconds (double precision).

    Handles the usual "M:SS.mmm" form (e.g. "1:29.708" -> 89.708) and a bare
    "SS.mmm" form. Empty strings and nulls become null. Uses only functions
    available on both DuckDB and Postgres (strpos, split_part).
#}
{% macro parse_laptime(col) -%}
    case
        when {{ col }} is null or {{ col }} = '' then null
        when strpos({{ col }}, ':') > 0 then
            cast(split_part({{ col }}, ':', 1) as double precision) * 60
            + cast(split_part({{ col }}, ':', 2) as double precision)
        else cast({{ col }} as double precision)
    end
{%- endmacro %}
