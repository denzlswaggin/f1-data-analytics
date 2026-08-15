-- Teammate qualifying gaps — the atomic unit of the driver-pace rating.
--
-- Method: teammates share identical machinery, so their qualifying gap isolates
-- driver pace from the car. For each race we compare the two drivers of a team
-- in the *last knockout session both set a time in* (Q3 if both reached it, else
-- Q2, else Q1) — the fair, apples-to-apples comparison.
--
-- The gap is expressed as an additive log-pace difference:
--     pace_gap = 100 * ( ln(driver_time) - ln(teammate_time) )
-- which is antisymmetric (gap_ab = -gap_ba) and additive across chains, so it
-- feeds directly into the global rating solver. Positive = driver slower.

with qualifying as (
    select * from {{ ref('stg_qualifying') }}
),

-- Only compare within teams that fielded exactly two cars that weekend, so each
-- driver has a single, unambiguous teammate.
team_race_counts as (
    select race_key, constructor_id, count(*) as n_cars
    from qualifying
    group by race_key, constructor_id
),

two_car_entries as (
    select q.*
    from qualifying as q
    inner join team_race_counts as trc
        on q.race_key = trc.race_key
        and q.constructor_id = trc.constructor_id
    where trc.n_cars = 2
),

paired as (
    select
        a.race_key,
        a.season,
        a.round,
        a.constructor_id,
        a.driver_id                                    as driver_id,
        b.driver_id                                    as teammate_id,
        a.q1_sec as a_q1, a.q2_sec as a_q2, a.q3_sec as a_q3,
        b.q1_sec as b_q1, b.q2_sec as b_q2, b.q3_sec as b_q3
    from two_car_entries as a
    inner join two_car_entries as b
        on a.race_key = b.race_key
        and a.constructor_id = b.constructor_id
        and a.driver_id <> b.driver_id
),

scored as (
    select
        race_key,
        season,
        round,
        constructor_id,
        driver_id,
        teammate_id,
        case
            when a_q3 is not null and b_q3 is not null then 'Q3'
            when a_q2 is not null and b_q2 is not null then 'Q2'
            when a_q1 is not null and b_q1 is not null then 'Q1'
        end as common_session,
        case
            when a_q3 is not null and b_q3 is not null then a_q3
            when a_q2 is not null and b_q2 is not null then a_q2
            when a_q1 is not null and b_q1 is not null then a_q1
        end as driver_time,
        case
            when a_q3 is not null and b_q3 is not null then b_q3
            when a_q2 is not null and b_q2 is not null then b_q2
            when a_q1 is not null and b_q1 is not null then b_q1
        end as teammate_time
    from paired
)

select
    race_key,
    season,
    round,
    constructor_id,
    driver_id,
    teammate_id,
    common_session,
    driver_time,
    teammate_time,
    100 * (ln(driver_time) - ln(teammate_time)) as pace_gap,
    driver_time < teammate_time                 as beat_teammate
from scored
where common_session is not null
    and driver_time > 0
    and teammate_time > 0
