"""Read-only publication, component and Madrid checks for race-control v3."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, nargs="?", default=Path("data/dashboard/latest.duckdb"))
    args = parser.parse_args()
    queries = {
        "unclean_eligible_events": "select count(*) from marts.race_control_events where eligible and not recovery_clean",
        "undersized_published_cohorts": "select count(*) from marts.race_control_events where time_eligible and time_comparable_driver_count < 5",
        "invalid_time_publication": """select count(*) from marts.race_control_impact
            where (field_adjusted_gap_gain_s is not null) != time_eligible
                or (time_eligible and (not eligible or event_type = 'Red Flag'
                    or lap_deficit_changed is distinct from false
                    or lap_deficit_before is null or lap_deficit_after is null
                    or time_comparable_driver_count < 5))""",
        "missing_time_exclusion_reason": "select count(*) from marts.race_control_impact where not time_eligible and coalesce(time_exclusion_reason, '') = ''",
        "event_driver_cohort_disagreement": """select count(*) from marts.race_control_impact d
            join marts.race_control_events e using(event_id)
            where d.time_comparable_driver_count != e.time_comparable_driver_count
                or (d.time_eligible and not e.time_eligible)""",
        "incorrect_centering": """select count(*) from (
            select field_adjusted_gap_gain_s, raw_gap_gain_s,
                median(raw_gap_gain_s) over(partition by event_id) as centre
            from marts.race_control_impact where time_eligible
        ) where abs(field_adjusted_gap_gain_s - (raw_gap_gain_s - centre)) > 0.000001""",
        "eligible_effect_without_value": """select count(*) from marts.race_control_effects
            where eligible and value is null""",
        "estimated_saving_without_interval": """select count(*)
            from marts.race_control_effects
            where effect_type in ('estimated_vsc_pit_saving',
                    'estimated_safety_car_pit_saving') and eligible
                and (evidence_class != 'estimated' or lower_bound is null or upper_bound is null
                    or lower_bound > value or upper_bound < value or sample_size < 5)""",
        "invalid_exact_pit_classification": """select count(*)
            from marts.race_control_impact
            where pit_eligible and (pit_timing_class not in
                    ('during_neutralisation', 'after_end')
                or pit_in_t_s is null or pit_out_t_s is null or pit_duration_sec is null
                or pit_out_t_s <= pit_in_t_s)""",
        "invalid_checkpoint_publication": """select count(*)
            from marts.race_control_checkpoints
            where eligible and (capture_offset_s is null or capture_offset_s > 2.0)""",
        "red_flag_gap_effect": """select count(*) from marts.race_control_effects
            where event_type = 'Red Flag' and eligible
                and effect_type in ('observed_gap_change', 'field_adjusted_gap_change',
                    'restart_gap_change', 'estimated_vsc_pit_saving',
                    'estimated_safety_car_pit_saving')""",
        "invalid_story_vocabulary": """select count(*) from marts.race_control_impact
            where story_status not in ('material_impact', 'no_material_effect', 'context_only')
                or story_direction not in ('benefit', 'loss', 'mixed', 'neutral', 'unknown')""",
        "invalid_story_counts": """select count(*) from marts.race_control_impact
            where material_effect_count < 0 or evaluated_effect_count < 0
                or material_effect_count > evaluated_effect_count
                or (story_status = 'material_impact' and material_effect_count = 0)
                or (story_status != 'material_impact' and material_effect_count > 0)
                or (story_status = 'no_material_effect' and evaluated_effect_count = 0)""",
    }
    with duckdb.connect(str(args.path), read_only=True) as connection:
        violations = {}
        for name, query in queries.items():
            row = connection.execute(query).fetchone()
            assert row is not None
            violations[name] = int(row[0])
        madrid_row = connection.execute(
            "select count(*) from marts.race_control_events where season=2026 and round=14"
        ).fetchone()
        assert madrid_row is not None
        madrid_present = bool(madrid_row[0])
        if madrid_present:
            golden_queries = {
                "madrid_focus_not_antonelli": """select count(*) from marts.race_control_events
                    where season=2026 and round=14 and event_type='VSC'
                        and (focus_driver_code != 'ANT' or pit_status != 'estimated')""",
                "madrid_pit_timing_mismatch": """select count(*) from (
                    select driver_code, pit_timing_class, pit_duration_sec
                    from marts.race_control_impact
                    where season=2026 and round=14 and event_type='VSC'
                        and driver_code in ('ANT','NOR')
                ) where (driver_code='ANT' and (pit_timing_class!='during_neutralisation'
                            or abs(pit_duration_sec-31.843) > 0.001))
                    or (driver_code='NOR' and (pit_timing_class!='after_end'
                            or abs(pit_duration_sec-35.134) > 0.001))""",
                "madrid_missing_supported_interval": """select case when count(*)=1 then 0 else 1 end
                    from marts.race_control_effects
                    where season=2026 and round=14 and driver_code='ANT'
                        and effect_type='estimated_vsc_pit_saving' and eligible
                        and lower_bound < value and value < upper_bound""",
            }
            for name, query in golden_queries.items():
                row = connection.execute(query).fetchone()
                assert row is not None
                violations[name] = int(row[0])
    print(json.dumps(violations, indent=2, sort_keys=True))
    if any(violations.values()):
        raise SystemExit("FAIL: race-control publication rules are inconsistent")
    print("PASS: race-control components, uncertainty, recovery and Madrid golden case")


if __name__ == "__main__":
    main()
