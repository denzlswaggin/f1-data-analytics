-- Per-stint degradation after removing the same-lap/same-compound peer pace.
-- The leave-one-out peer mean absorbs shared fuel burn and track evolution while
-- avoiding the driver's own lap leaking into its baseline.
with context as (
    select
        *,
        sum(lap_time_sec) over (
            partition by season, round, lap_number, compound
        ) as field_lap_sum_sec,
        count(*) over (
            partition by season, round, lap_number, compound
        ) as field_lap_size
    from {{ ref('mart_lap_times') }}
    where tyre_life >= 2
        and lap_number > 1
        and compound not in ('UNKNOWN', 'None', 'nan')
),

residuals as (
    select
        *,
        lap_time_sec
            - (field_lap_sum_sec - lap_time_sec) / (field_lap_size - 1) as residual_sec
    from context
    where field_lap_size >= 3
),

ranked as (
    select
        *,
        row_number() over (
            partition by season, round, driver_code, stint order by tyre_life
        ) as early_rank,
        row_number() over (
            partition by season, round, driver_code, stint order by tyre_life desc
        ) as late_rank
    from residuals
),

fitted as (
    select
        season,
        round,
        driver_code,
        stint,
        max(race_name) as race_name,
        max(driver_id) as driver_id,
        max(driver_name) as driver_name,
        max(team) as team,
        max(compound) as compound,
        count(*) as comparable_laps,
        max(tyre_life) - min(tyre_life) + 1 as stint_length,
        regr_slope(residual_sec, tyre_life) as adjusted_deg_sec_per_lap,
        avg(case when early_rank <= 3 then residual_sec end) as early_residual_sec,
        avg(case when late_rank <= 3 then residual_sec end) as late_residual_sec
    from ranked
    group by season, round, driver_code, stint
    having count(*) >= 5
)

select
    fitted.*,
    raw.deg_sec_per_lap as raw_deg_sec_per_lap,
    fitted.adjusted_deg_sec_per_lap - raw.deg_sec_per_lap as adjustment_delta,
    fitted.late_residual_sec - fitted.early_residual_sec as late_stint_loss_sec,
    case
        when fitted.late_residual_sec - fitted.early_residual_sec >= 0.8 then true
        else false
    end as cliff_signal
from fitted
left join {{ ref('mart_stint_degradation') }} as raw
    on raw.season = fitted.season
    and raw.round = fitted.round
    and raw.driver_code = fitted.driver_code
    and raw.stint = fitted.stint
