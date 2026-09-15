{% macro create_optional_openf1_timing_sources() %}
    {% if not var('load_ci_seeds', false) | as_bool %}
    {% set ddl %}
        create schema if not exists raw;
        create table if not exists raw.openf1_positions (
            season integer, round integer, session varchar, session_key bigint,
            meeting_key bigint, session_time_sec double precision, source_utc varchar,
            driver_number varchar, driver_code varchar, position integer,
            source_sha256 varchar
        );
        create table if not exists raw.openf1_intervals (
            season integer, round integer, session varchar, session_key bigint,
            meeting_key bigint, session_time_sec double precision, source_utc varchar,
            driver_number varchar, driver_code varchar, gap_to_leader_raw varchar,
            gap_to_ahead_raw varchar, gap_to_leader_s double precision,
            gap_to_ahead_s double precision, leader_lap_deficit integer,
            ahead_lap_deficit integer, source_sha256 varchar
        );
        create table if not exists raw.openf1_race_control (
            season integer, round integer, session varchar, session_key bigint,
            meeting_key bigint, session_time_sec double precision, source_utc varchar,
            category varchar, flag varchar, message varchar, lap_number integer,
            source_sha256 varchar
        );
        create table if not exists raw.openf1_timing_audit (
            season integer, round integer, session varchar, session_key bigint,
            meeting_key bigint, status varchar, anchor_count integer,
            inlier_anchor_count integer, anchor_driver_count integer,
            inlier_ratio double precision, alignment_p95_s double precision,
            clock_zero_utc varchar, exclusion_reason varchar, position_row_count bigint,
            interval_row_count bigint, control_row_count bigint
        )
    {% endset %}
    {% do run_query(ddl) %}
    {% endif %}
{% endmacro %}
