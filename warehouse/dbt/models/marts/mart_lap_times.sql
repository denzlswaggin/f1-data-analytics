-- Green-flag race laps with tyre context — powers the race-pace / tyre-stint
-- dashboard page. One row per driver per racing lap, valid timed laps only.
{{
    config(
        post_hook="{% if target.type == 'postgres' %}create index if not exists mart_lap_times_race_idx on {{ this }} (race_name){% endif %}"
    )
}}
with laps as (
    select * from {{ ref('stg_laps') }}
),

races as (
    select race_key, season, round, race_name from {{ ref('stg_races') }}
)

select
    laps.season,
    laps.round,
    races.race_name,
    laps.driver_code,
    laps.team,
    laps.lap_number,
    laps.stint,
    laps.compound,
    laps.tyre_life,
    laps.position,
    laps.lap_time_sec
from laps
left join races
    on laps.season = races.season
    and laps.round = races.round
where laps.session = 'R'
    and laps.lap_time_sec is not null
    -- track_status '1' = green flag (no SC/VSC/yellow); clean pace laps only.
    and laps.track_status = '1'
