-- Teammate race-pace gaps — the Sunday counterpart to int_teammate_quali_gaps.
--
-- Method: teammates share identical machinery, so their race-lap gap isolates
-- driver pace from the car. But race pace carries confounds qualifying does not
-- (fuel load, tyre age, compound, traffic, strategy), so laps are only compared
-- like-for-like: teammates are paired on the *same lap number* — identical fuel
-- load and track evolution — restricted to green-flag laps on the *same
-- compound* at a similar tyre age, with in/out laps and outliers removed.
--
-- The per-lap gap uses the same additive log-pace form as the qualifying model:
--     lap_gap = 100 * ( ln(driver_time) - ln(teammate_time) )
-- and the surviving laps are averaged into one row per driver per race — the
-- exact grain of int_teammate_quali_gaps, so the same rating solver consumes
-- this unchanged. Both directions of each pairing are emitted, and every filter
-- is symmetric in the two drivers, so pace_gap stays antisymmetric.
--
-- The comparability thresholds are dbt vars (see dbt_project.yml) — they trade
-- sample size against like-for-like strictness and are meant to be tuned once
-- real coverage is known.

-- Materialised as a table, unlike the rest of the intermediate layer. This model
-- self-joins ~100k FastF1 lap rows; as a view that join is re-executed by every
-- one of its six data tests and again by each Python reader (the pace-profile
-- build and `validate --race`). On DuckDB that is free, but on Postgres the test
-- pass alone ran past eleven minutes. The quali gaps stay a view — they sit on
-- ~8k qualifying rows, where the join is trivial.
{{ config(materialized='table') }}

{% set max_tyre_delta = var('race_gap_max_tyre_delta') %}
{% set outlier_pct = var('race_gap_outlier_pct') %}
{% set min_laps = var('race_gap_min_laps') %}

with laps as (
    select
        season,
        round,
        driver_code,
        team,
        lap_number,
        stint,
        compound,
        tyre_life,
        lap_time_sec
    from {{ ref('stg_laps') }}
    where session = 'R'
        and lap_time_sec is not null
        and lap_time_sec > 0
        -- track_status '1' = green flag (no SC/VSC/yellow); clean pace laps only.
        and track_status = '1'
        -- FastF1 reports an unknown compound as the *strings* 'None'/'nan', not a
        -- SQL null, so `is not null` alone lets them through — and two teammates
        -- both carrying 'None' would then be compared as if on a matching tyre
        -- when their actual compounds are simply unknown.
        and compound is not null
        and compound not in ('None', 'nan', 'UNKNOWN')
        and tyre_life is not null
),

-- stg_laps carries no pit-in/pit-out column, so in- and out-laps are derived:
-- they are the first and last lap of each stint. (A final stint's last lap is
-- the chequered flag rather than an in-lap; dropping it costs one lap and keeps
-- the rule uniform.)
stint_bounds as (
    select
        *,
        min(lap_number) over (partition by season, round, driver_code, stint) as stint_first_lap,
        max(lap_number) over (partition by season, round, driver_code, stint) as stint_last_lap
    from laps
),

racing_laps as (
    select *
    from stint_bounds
    where lap_number > 1                    -- a standing start is not race pace
        and lap_number > stint_first_lap    -- out-lap
        and lap_number < stint_last_lap     -- in-lap
),

-- Only teams that fielded exactly two cars, so each driver has a single
-- unambiguous teammate (mirrors int_teammate_quali_gaps).
team_race_counts as (
    select season, round, team, count(distinct driver_code) as n_cars
    from racing_laps
    group by season, round, team
),

two_car_entries as (
    select rl.*
    from racing_laps as rl
    inner join team_race_counts as trc
        on rl.season = trc.season
        and rl.round = trc.round
        and rl.team = trc.team
    where trc.n_cars = 2
),

-- Pair teammates on the same lap number, on the same compound at a comparable
-- tyre age. Compound is the single most important control: a soft/hard split is
-- worth ~1 s/lap, which would swamp the driver signal entirely.
paired_laps as (
    select
        a.season,
        a.round,
        a.team,
        a.driver_code                                   as driver_code,
        b.driver_code                                   as teammate_code,
        a.lap_number,
        100 * (ln(a.lap_time_sec) - ln(b.lap_time_sec)) as lap_gap
    from two_car_entries as a
    inner join two_car_entries as b
        on a.season = b.season
        and a.round = b.round
        and a.team = b.team
        and a.lap_number = b.lap_number
        and a.driver_code <> b.driver_code
    where a.compound = b.compound
        and abs(a.tyre_life - b.tyre_life) <= {{ max_tyre_delta }}
),

-- Traffic, lock-ups, damage and off-track moments are not pace.
comparable_laps as (
    select *
    from paired_laps
    where abs(lap_gap) <= {{ outlier_pct }}
),

aggregated as (
    select
        season,
        round,
        team,
        driver_code,
        teammate_code,
        count(*)     as n_laps,
        avg(lap_gap) as pace_gap
    from comparable_laps
    group by season, round, team, driver_code, teammate_code
    -- A handful of comparable laps is noise, not an observation of race pace.
    having count(*) >= {{ min_laps }}
),

races as (
    select race_key, season, round, race_name from {{ ref('stg_races') }}
),

-- Bridge FastF1's 3-letter code to the Ergast driver_id, so these gaps share a
-- key with int_teammate_quali_gaps and the two ratings can be joined.
driver_codes as (
    select season, driver_code, driver_id from {{ ref('stg_driver_codes') }}
)

select
    races.race_key,
    agg.season,
    agg.round,
    races.race_name,
    agg.team,
    dc.driver_id             as driver_id,
    tc.driver_id             as teammate_id,
    agg.driver_code,
    agg.teammate_code,
    agg.n_laps,
    agg.pace_gap,
    agg.pace_gap < 0         as beat_teammate
from aggregated as agg
inner join races
    on agg.season = races.season
    and agg.round = races.round
inner join driver_codes as dc
    on agg.season = dc.season
    and agg.driver_code = dc.driver_code
inner join driver_codes as tc
    on agg.season = tc.season
    and agg.teammate_code = tc.driver_code
