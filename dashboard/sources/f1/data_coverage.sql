-- Honest coverage metadata for every public dashboard section. `latest_event_date`
-- is the newest race represented by the data, not the ingestion refresh time.
with races as (
    select race.season, race.round, race.race_name, race.race_date
    from staging.stg_races as race
    where exists (
        select 1
        from marts.mart_lap_times as laps
        where laps.season = race.season and laps.round = race.round
    )
),

fastest_telemetry_laps as (
    select
        t.season,
        t.round,
        t.driver_code,
        arg_min(t.lap_number, l.lap_time_sec) as lap_number
    from marts.mart_lap_telemetry t
    join marts.mart_lap_times l
        on l.season = t.season
        and l.round = t.round
        and l.driver_code = t.driver_code
        and l.lap_number = t.lap_number
    group by t.season, t.round, t.driver_code
),

coverage as (
    select
        'driver_rating' as section,
        cast(null as integer) as season,
        cast(null as integer) as round,
        cast(null as varchar) as race_label,
        count(*) as sample_rows,
        count(distinct driver_id) as entity_count,
        count(distinct race_key) as race_count,
        count(*) as usable_samples,
        min(season) as first_season,
        max(season) as last_season
    from intermediate.int_teammate_quali_gaps

    union all

    select
        'pace_profile', null, null, null, count(*), count(distinct driver_id),
        count(distinct race_key), sum(n_laps), min(season), max(season)
    from intermediate.int_teammate_race_gaps

    union all

    select
        'race_pace', season, round, cast(season as varchar) || ' ' || race_name,
        count(*), count(distinct driver_code), 1, count(*), season, season
    from marts.mart_lap_times
    group by season, round, race_name

    union all

    select
        'race_story', season, round, cast(season as varchar) || ' ' || race_name,
        count(*), count(distinct driver_code), 1, sum(pace_samples), season, season
    from marts.mart_race_story
    group by season, round, race_name

    union all

    select
        'pit_cycle', season, round, cast(season as varchar) || ' ' || race_name,
        count(*), count(distinct driver_id), 1, count(positions_gained), season, season
    from marts.mart_pit_strategy
    group by season, round, race_name

    union all

    select
        'tyre_strategy', season, round, cast(season as varchar) || ' ' || race_name,
        count(*), count(distinct driver_code), 1, count(deg_sec_per_lap), season, season
    from marts.mart_stint_strategy
    group by season, round, race_name

    union all

    select
        'weather_slope', null, null, null, count(*), count(distinct compound),
        count(distinct case when weather_bucket is not null then cast(season as varchar) || '-' || cast(round as varchar) end),
        count(case when weather_bucket is not null then 1 end), min(season), max(season)
    from marts.mart_weather_degradation

    union all

    select
        'speed_trap', season, round, cast(season as varchar) || ' ' || race_name,
        count(*), count(distinct driver_code), 1, sum(n_laps), season, season
    from marts.mart_speed_trap
    group by season, round, race_name

    union all

    select
        'telemetry', f.season, f.round, cast(f.season as varchar) || ' ' || r.race_name,
        count(*), count(distinct f.driver_code), 1, count(*), f.season, f.season
    from fastest_telemetry_laps f
    join races r on r.season = f.season and r.round = f.round
    group by f.season, f.round, r.race_name

    union all

    select
        'race_replay', rr.season, rr.round, cast(rr.season as varchar) || ' ' || r.race_name,
        count(*), count(distinct rr.driver_code), 1,
        cast(max(rr.t_s) - min(rr.t_s) as bigint), rr.season, rr.season
    from marts.race_replay rr
    join races r on r.season = rr.season and r.round = rr.round
    group by rr.season, rr.round, r.race_name

    union all

    select
        'traffic_pace', season, round, cast(season as varchar) || ' ' || race_name,
        sum(eligible_laps), count(distinct driver_code), 1,
        sum(clean_air_laps + traffic_laps), season, season
    from marts.traffic_adjusted_pace
    group by season, round, race_name

    union all

    select
        'pace_consistency', season, round, cast(season as varchar) || ' ' || race_name,
        sum(candidate_laps), count(distinct driver_code), 1,
        sum(modelled_laps), season, season
    from marts.pace_consistency
    group by season, round, race_name

    union all

    select
        'tyre_warmup', season, round, cast(season as varchar) || ' ' || race_name,
        count(*), count(distinct driver_code), 1,
        count(*) filter (where warmup_eligible), season, season
    from marts.tyre_warmup
    group by season, round, race_name

    union all

    select
        'pit_timing', season, round, cast(season as varchar) || ' ' || race_name,
        count(*), count(distinct driver_code), 1,
        count(*) filter (where eligible), season, season
    from marts.pit_timing_sensitivity
    group by season, round, race_name

    union all

    select
        'pit_window', season, round, cast(season as varchar) || ' ' || race_name,
        count(*), count(*), 1,
        count(*) filter (where eligible), season, season
    from marts.pit_window_effectiveness
    group by season, round, race_name

    union all

    select
        'race_control', season, round, cast(season as varchar) || ' ' || race_name,
        count(*), count(distinct event_id), 1,
        sum(eligible_driver_count), season, season
    from marts.race_control_events
    group by season, round, race_name

    union all

    select
        'racecraft', season, round, cast(season as varchar) || ' ' || race_name,
        count(*), count(distinct attacker_code), 1,
        count(*) filter (where eligible), season, season
    from marts.racecraft_battles
    group by season, round, race_name
)

select
    coverage.*,
    max(races.race_date) as latest_event_date
from coverage
left join races
    on (coverage.season is null and races.season between coverage.first_season and coverage.last_season)
    or (races.season = coverage.season and races.round = coverage.round)
group by all
order by section, race_label
