"""Build immutable DuckDB snapshots for the static Evidence dashboard.

The operational warehouse remains the system of record.  A dashboard build
consumes a compact, read-only snapshot instead of running a historical backfill
inside the Pages workflow.  Snapshots can be produced from either development
DuckDB or production Postgres and optionally published to object storage.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
from analytics.racecraft_integrity import RECEIPT_COLUMNS, validate_snapshot_processing
from sqlalchemy import create_engine, inspect, text

from ingestion.config import FIRST_SEASON, LAST_SEASON, Settings, get_settings
from ingestion.snapshot_coverage import (
    materialize_source_coverage,
    validate_partition_preservation,
    validate_source_coverage,
)

DASHBOARD_SCHEMAS = ("staging", "intermediate", "marts")

# This is the serving contract, not merely a minimum snapshot smoke test. Every
# public Evidence source must be able to compile against a freshly exported
# database. Optional datasets still materialise an empty table with the declared
# columns, so their absence is always a broken pipeline rather than "no data".
DASHBOARD_CONTRACT: dict[tuple[str, str], set[str]] = {
    ("marts", "source_coverage"): {
        "source_sha256",
        "resource",
        "season",
        "round",
        "status",
        "row_count",
        "provenance",
        "reason",
    },
    ("marts", "racecraft_processing"): RECEIPT_COLUMNS,
    ("marts", "pit_lap_context"): {
        "season",
        "round",
        "driver_code",
        "lap_number",
        "is_pit_in_lap",
        "is_pit_out_lap",
        "is_pit_boundary",
        "pit_context_source",
        "pit_context_status",
        "pit_exclusion_reason",
    },
    ("staging", "stg_races"): {"season", "round", "race_name", "race_date"},
    ("staging", "stg_driver_codes"): {
        "season",
        "driver_code",
        "driver_id",
        "driver_name",
    },
    ("staging", "stg_results"): {
        "season",
        "round",
        "driver_code",
        "driver_id",
        "driver_name",
        "constructor_id",
        "grid_position",
        "finish_position",
        "position_text",
        "status",
        "is_classified",
    },
    ("staging", "stg_laps"): {
        "season",
        "round",
        "session",
        "driver_code",
        "team",
        "lap_number",
        "stint",
        "compound",
        "tyre_life",
        "lap_start_sec",
        "lap_time_sec",
        "pit_in_time_sec",
        "pit_out_time_sec",
    },
    ("staging", "stg_race_control"): {
        "season",
        "round",
        "session",
        "session_time_sec",
        "category",
        "flag",
        "scope",
        "message",
        "driver_code",
        "lap",
    },
    ("staging", "stg_team_radio"): {
        "season",
        "round",
        "session_time_sec",
        "session",
        "driver_code",
        "recording_url",
        "transcript",
    },
    ("staging", "stg_weather"): {
        "season",
        "round",
        "session",
        "time_sec",
        "air_temp",
        "track_temp",
        "humidity",
        "pressure",
        "wind_speed",
        "wind_direction",
        "is_raining",
    },
    ("staging", "constructor_colors"): {"team", "team_color"},
    ("intermediate", "int_teammate_quali_gaps"): {
        "race_key",
        "season",
        "driver_id",
        "teammate_id",
        "pace_gap",
    },
    ("intermediate", "int_teammate_race_gaps"): {
        "race_key",
        "season",
        "driver_id",
        "teammate_id",
        "pace_gap",
        "n_laps",
    },
    ("marts", "driver_ratings"): {
        "rank",
        "driver_id",
        "driver_name",
        "nationality",
        "rating",
        "rating_lo",
        "rating_hi",
        "n_boot",
        "pace_deficit",
        "n_comparisons",
        "n_seasons",
        "first_season",
        "last_season",
    },
    ("marts", "driver_ratings_v2"): {
        "season",
        "rank",
        "driver_id",
        "driver_name",
        "nationality",
        "rating",
        "rating_lo",
        "rating_hi",
        "n_boot",
        "pace_deficit",
        "form_delta",
        "n_comparisons",
    },
    ("marts", "driver_pace_profile"): {
        "delta_lo",
        "delta_hi",
        "bootstrap_valid_samples",
        "bootstrap_samples",
        "interval_eligible",
        "delta_rank",
        "driver_id",
        "driver_name",
        "nationality",
        "quali_rating",
        "race_rating",
        "delta",
        "quali_rank",
        "race_rank",
        "n_quali_comparisons",
        "n_race_comparisons",
        "n_seasons",
        "first_season",
        "last_season",
    },
    ("marts", "mart_driver_season_pace"): {
        "driver_id",
        "driver_name",
        "season",
        "races_compared",
        "teammate_quali_wins",
        "teammate_win_pct",
        "mean_pace_gap",
        "stddev_pace_gap",
    },
    ("marts", "mart_lap_times"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "team",
        "lap_number",
        "stint",
        "compound",
        "tyre_life",
        "position",
        "lap_time_sec",
    },
    ("marts", "mart_pit_strategy"): {
        "season",
        "round",
        "race_name",
        "driver_id",
        "driver_name",
        "stop_number",
        "pit_lap",
        "duration_sec",
        "position_before",
        "position_after",
        "positions_gained",
    },
    ("marts", "mart_speed_trap"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "driver_name",
        "team",
        "n_laps",
        "top_speed_kph",
        "avg_speed_kph",
    },
    ("marts", "mart_stint_strategy"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "driver_name",
        "team",
        "stint",
        "compound",
        "start_lap",
        "end_lap",
        "stint_laps",
        "tyre_life_end",
        "started_fresh",
        "finish_position",
        "deg_sec_per_lap",
    },
    ("marts", "mart_tyre_degradation"): {
        "season",
        "round",
        "race_name",
        "compound",
        "n_laps",
        "deg_sec_per_lap",
        "best_lap_sec",
        "avg_lap_sec",
    },
    ("marts", "mart_weather_degradation"): {
        "season",
        "round",
        "race_name",
        "compound",
        "weather_bucket",
        "avg_track_temp",
        "avg_air_temp",
        "n_laps",
        "deg_sec_per_lap",
        "avg_lap_sec",
    },
    ("marts", "mart_lap_telemetry"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "driver_name",
        "lap_number",
        "compound",
        "distance_m",
        "speed_kph",
        "throttle",
        "brake",
        "drs",
        "gear",
        "x",
        "y",
    },
    ("marts", "driver_dna_evidence"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "driver_name",
        "team",
        "teammate_code",
        "teammate_name",
        "driver_lap_number",
        "teammate_lap_number",
        "compound",
        "driver_tyre_life",
        "teammate_tyre_life",
        "driver_track_status",
        "teammate_track_status",
        "lap_number_gap",
        "tyre_life_gap",
        "pair_selection_score",
        "common_points",
        "valid_coverage_pct",
        "throttle_corrections",
        "gear_anomalies",
        "eligible",
        "exclusion_reason",
        "full_throttle_share_delta",
        "coasting_share_delta",
        "braking_share_delta",
        "brake_onset_speed_kph_delta",
        "low_speed_kph_delta",
        "full_throttle_share_z",
        "coasting_share_z",
        "braking_share_z",
        "brake_onset_speed_kph_z",
        "low_speed_kph_z",
        "methodology_version",
    },
    ("marts", "driver_dna_profile"): {
        "from_season",
        "to_season",
        "driver_code",
        "driver_name",
        "n_comparisons",
        "n_teammates",
        "n_seasons",
        "first_season",
        "last_season",
        "confidence",
        "full_throttle_share",
        "full_throttle_share_lo",
        "full_throttle_share_hi",
        "coasting_share",
        "coasting_share_lo",
        "coasting_share_hi",
        "braking_share",
        "braking_share_lo",
        "braking_share_hi",
        "brake_onset_speed_kph",
        "brake_onset_speed_kph_lo",
        "brake_onset_speed_kph_hi",
        "low_speed_kph",
        "low_speed_kph_lo",
        "low_speed_kph_hi",
        "bootstrap_samples",
        "methodology_version",
    },
    ("marts", "driver_dna_microsectors"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "driver_name",
        "teammate_code",
        "teammate_name",
        "driver_lap_number",
        "teammate_lap_number",
        "compound",
        "segment_number",
        "start_distance_m",
        "end_distance_m",
        "segment_delta_sec",
        "driver_speed_kph",
        "teammate_speed_kph",
        "driver_throttle",
        "teammate_throttle",
        "driver_brake_share",
        "teammate_brake_share",
        "x",
        "y",
        "methodology_version",
    },
    ("marts", "race_replay"): {
        "season",
        "round",
        "driver_code",
        "t_s",
        "x",
        "y",
        "running_order",
        "gap_to_leader_s",
        "gap_to_ahead_s",
        "lap_number",
        "lap_progress",
        "stint",
        "compound",
        "tyre_life",
        "running_order_source",
        "running_order_confidence",
        "running_order_observed_t_s",
        "gap_source",
        "gap_confidence",
        "gap_observed_t_s",
    },
    ("marts", "traffic_adjusted_laps"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "team",
        "lap_number",
        "stint",
        "compound",
        "tyre_life",
        "lap_time_sec",
        "context_samples",
        "valid_context_samples",
        "traffic_samples",
        "traffic_share",
        "clean_air_share",
        "replay_coverage_pct",
        "median_gap_to_ahead_s",
        "air_state",
        "peer_lap_avg_sec",
        "peer_lap_median_sec",
        "peer_count",
        "controlled_pace_delta_sec",
        "matched_clean_laps",
        "matched_clean_delta_sec",
        "paired_traffic_delta_sec",
    },
    ("marts", "traffic_adjusted_pace"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "team",
        "eligible_laps",
        "clean_air_laps",
        "traffic_laps",
        "mixed_laps",
        "matched_traffic_laps",
        "traffic_exposure_pct",
        "replay_coverage_pct",
        "observed_controlled_pace_delta_sec",
        "clean_air_controlled_pace_delta_sec",
        "traffic_adjusted_pace_delta_sec",
        "traffic_controlled_pace_delta_sec",
        "traffic_associated_delta_sec_per_lap",
        "traffic_associated_p25_sec",
        "traffic_associated_p75_sec",
        "clean_air_eligible",
        "clean_air_confidence",
        "traffic_association_eligible",
        "traffic_association_confidence",
        "confidence",
        "traffic_gap_threshold_s",
        "clean_air_gap_threshold_s",
        "methodology_version",
    },
    ("marts", "pace_consistency"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "driver_name",
        "team",
        "candidate_laps",
        "modelled_laps",
        "excluded_laps",
        "candidate_stints",
        "modelled_stints",
        "robust_consistency_sec",
        "robust_consistency_pct",
        "p90_slow_tail_sec",
        "slow_lap_threshold_sec",
        "unexplained_slow_laps",
        "unexplained_slow_lap_share_pct",
        "unexplained_slow_lap_cost_sec",
        "slow_lap_cost_per_10_laps_sec",
        "worst_residual_sec",
        "replay_coverage_pct",
        "consistency_eligible",
        "exclusion_reason",
        "confidence",
        "methodology_version",
    },
    ("marts", "pace_consistency_laps"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "driver_name",
        "team",
        "lap_number",
        "stint",
        "compound",
        "tyre_life",
        "lap_time_sec",
        "air_state",
        "replay_coverage_pct",
        "controlled_pace_delta_sec",
        "expected_controlled_pace_delta_sec",
        "pace_residual_sec",
        "absolute_residual_sec",
        "slow_lap_threshold_sec",
        "unexplained_slow_excess_sec",
        "is_unexplained_slow_lap",
        "lap_eligible",
        "lap_exclusion_reason",
        "stint_clean_laps",
        "stint_slope_sec_per_tyre_lap",
        "stint_intercept_sec",
        "methodology_version",
    },
    ("marts", "pit_timing_sensitivity"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "driver_name",
        "team",
        "stop_number",
        "actual_pit_lap",
        "actual_out_lap",
        "pit_duration_sec",
        "official_pit_match",
        "old_stint",
        "new_stint",
        "old_compound",
        "new_compound",
        "new_tyre_fresh",
        "window_start_lap",
        "window_end_lap",
        "best_supported_shift_laps",
        "best_hypothetical_pit_lap",
        "estimated_gain_vs_actual_sec",
        "best_delta_p25_sec",
        "best_delta_p75_sec",
        "best_shift_win_pct",
        "bootstrap_requested_samples",
        "bootstrap_valid_samples",
        "bootstrap_attempted_samples",
        "boundary_minimum",
        "best_old_extrapolation_laps",
        "best_new_extrapolation_laps",
        "actual_old_extrapolation_laps",
        "actual_new_extrapolation_laps",
        "best_earlier_delta_sec",
        "best_later_delta_sec",
        "supported_scenarios",
        "old_reference_laps",
        "new_mature_reference_laps",
        "warmup_profile_laps",
        "old_slope_sec_per_tyre_lap",
        "new_slope_sec_per_stint_lap",
        "old_model_mad_sec",
        "new_model_mad_sec",
        "replay_coverage_pct",
        "field_peer_count_median",
        "timing_signal",
        "eligible",
        "exclusion_reason",
        "confidence",
        "methodology_version",
    },
    ("marts", "pit_timing_scenarios"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "driver_name",
        "team",
        "stop_number",
        "actual_pit_lap",
        "actual_out_lap",
        "shift_laps",
        "hypothetical_pit_lap",
        "hypothetical_out_lap",
        "estimated_cost_index_sec",
        "delta_vs_actual_sec",
        "estimated_gain_vs_actual_sec",
        "delta_p25_sec",
        "delta_p75_sec",
        "old_tyre_extension_laps",
        "old_extrapolation_laps",
        "new_extrapolation_laps",
        "supported",
        "exclusion_reason",
        "methodology_version",
    },
    ("marts", "tyre_warmup"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "driver_name",
        "team",
        "stint",
        "compound",
        "is_fresh_tyre",
        "out_lap",
        "stint_start_lap",
        "stint_end_lap",
        "stint_laps",
        "contiguous_stint_transition",
        "clean_evaluation_laps",
        "traffic_evaluation_laps",
        "mature_reference_laps",
        "baseline_slope_sec_per_lap",
        "baseline_intercept_sec",
        "baseline_mad_sec",
        "first_flying_warmup_loss_sec",
        "second_flying_warmup_loss_sec",
        "first_two_lap_warmup_cost_sec",
        "stable_band_sec",
        "stable_window_start_lap",
        "time_to_pace_laps",
        "first_observed_confirmation_laps",
        "confirmation_history_complete",
        "settling_status",
        "stable_pace_achieved",
        "right_censored",
        "observation_complete",
        "warmup_eligible",
        "crossover_eligible",
        "exclusion_reason",
        "confidence",
        "replay_coverage_pct",
        "methodology_version",
    },
    ("marts", "tyre_warmup_laps"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "driver_name",
        "team",
        "stint",
        "compound",
        "is_fresh_tyre",
        "out_lap",
        "lap_number",
        "post_stop_offset",
        "tyre_life",
        "lap_time_sec",
        "track_status",
        "air_state",
        "replay_coverage_pct",
        "traffic_share",
        "median_gap_to_ahead_s",
        "controlled_pace_delta_sec",
        "expected_mature_delta_sec",
        "warmup_loss_sec",
        "used_for_baseline",
        "within_stable_band",
        "lap_eligible",
        "lap_exclusion_reason",
        "methodology_version",
    },
    ("marts", "pit_window_effectiveness"): {
        "season",
        "round",
        "race_name",
        "stop_number",
        "early_driver_code",
        "early_driver_name",
        "early_team",
        "late_driver_code",
        "late_driver_name",
        "late_team",
        "early_pit_lap",
        "late_pit_lap",
        "stop_separation_laps",
        "checkpoint_before_lap",
        "checkpoint_after_lap",
        "early_old_compound",
        "early_new_compound",
        "late_old_compound",
        "late_new_compound",
        "early_new_tyre_fresh",
        "late_new_tyre_fresh",
        "position_before_early",
        "position_before_late",
        "position_after_early",
        "position_after_late",
        "gap_before_sec",
        "gap_after_sec",
        "net_time_gain_sec",
        "early_stop_duration_sec",
        "late_stop_duration_sec",
        "stop_duration_delta_sec",
        "on_track_gain_sec",
        "position_flip",
        "window_green",
        "eligible",
        "exclusion_reason",
        "confidence",
        "opportunity_type",
        "outcome_label",
        "methodology_version",
    },
    ("marts", "race_control_events"): {
        "season",
        "round",
        "race_name",
        "event_id",
        "event_number",
        "event_type",
        "start_t_s",
        "end_t_s",
        "post_checkpoint_t_s",
        "deployment_lap",
        "end_lap",
        "post_checkpoint_lap",
        "duration_s",
        "event_status",
        "recovery_clean",
        "pre_driver_count",
        "post_driver_count",
        "eligible_driver_count",
        "time_comparable_driver_count",
        "time_eligible",
        "time_exclusion_reason",
        "intervention_stop_count",
        "recovery_stop_count",
        "position_gainer_count",
        "position_loser_count",
        "position_status",
        "gap_status",
        "pit_status",
        "restart_status",
        "tyre_status",
        "focus_driver_code",
        "eligible",
        "exclusion_reason",
        "confidence",
        "methodology_version",
    },
    ("marts", "race_control_impact"): {
        "season",
        "round",
        "race_name",
        "event_id",
        "event_number",
        "event_type",
        "driver_code",
        "driver_name",
        "team",
        "position_before",
        "position_after",
        "positions_gained",
        "position_before_source",
        "position_after_source",
        "position_before_confidence",
        "position_after_confidence",
        "position_before_observed_t_s",
        "position_after_observed_t_s",
        "position_evidence_class",
        "gap_to_leader_before_s",
        "gap_to_leader_after_s",
        "raw_gap_gain_s",
        "field_adjusted_gap_gain_s",
        "gap_before_source",
        "gap_after_source",
        "gap_before_confidence",
        "gap_after_confidence",
        "gap_before_observed_t_s",
        "gap_after_observed_t_s",
        "gap_evidence_class",
        "lap_before",
        "lap_after",
        "lap_deficit_before",
        "lap_deficit_after",
        "lap_deficit_changed",
        "time_comparable_driver_count",
        "time_eligible",
        "time_exclusion_reason",
        "stint_before",
        "stint_after",
        "compound_before",
        "compound_after",
        "tyre_life_before",
        "tyre_life_after",
        "pitted_during_intervention",
        "pitted_during_recovery",
        "pit_timing_class",
        "pit_in_t_s",
        "pit_out_t_s",
        "pit_duration_sec",
        "stop_count",
        "tyre_changed_during_suspension",
        "active_after",
        "position_eligible",
        "gap_eligible",
        "pit_eligible",
        "restart_eligible",
        "tyre_eligible",
        "story_status",
        "story_direction",
        "story_reason",
        "material_effect_count",
        "evaluated_effect_count",
        "focus_rank",
        "eligible",
        "exclusion_reason",
        "confidence",
        "outcome_label",
        "timing_before_offset_s",
        "timing_after_offset_s",
        "methodology_version",
    },
    ("marts", "race_control_checkpoints"): {
        "season",
        "round",
        "race_name",
        "event_id",
        "event_number",
        "event_type",
        "driver_code",
        "driver_name",
        "team",
        "checkpoint_type",
        "checkpoint_order",
        "checkpoint_t_s",
        "lap_number",
        "lap_progress",
        "running_order",
        "gap_to_leader_s",
        "running_order_source",
        "running_order_confidence",
        "running_order_observed_t_s",
        "gap_source",
        "gap_confidence",
        "gap_observed_t_s",
        "evidence_class",
        "stint",
        "compound",
        "tyre_life",
        "capture_offset_s",
        "source",
        "eligible",
        "exclusion_reason",
        "methodology_version",
    },
    ("marts", "race_control_effects"): {
        "season",
        "round",
        "race_name",
        "event_id",
        "event_number",
        "event_type",
        "driver_code",
        "effect_type",
        "effect_scope",
        "value",
        "lower_bound",
        "upper_bound",
        "unit",
        "evidence_class",
        "confidence",
        "sample_size",
        "eligible",
        "exclusion_reason",
        "methodology_version",
    },
    ("marts", "race_overtakes"): {
        "season",
        "round",
        "t_s",
        "for_position",
        "passer_code",
        "passed_code",
        "gap_at_pass_s",
        "confidence",
        "evidence",
        "reason",
    },
    ("marts", "racecraft_battles"): {
        "season",
        "round",
        "race_name",
        "battle_id",
        "battle_number",
        "attacker_code",
        "attacker_name",
        "attacker_team",
        "defender_code",
        "defender_name",
        "defender_team",
        "same_team",
        "start_t_s",
        "end_t_s",
        "duration_s",
        "pressure_seconds",
        "longest_pressure_run_s",
        "release_run_s",
        "contact_seconds",
        "start_lap",
        "end_lap",
        "laps_spanned",
        "position_contested",
        "valid_samples",
        "pressure_samples",
        "coverage_pct",
        "same_lap_deficit_share_pct",
        "min_gap_s",
        "median_gap_s",
        "outcome",
        "terminal_reason",
        "converted",
        "defender_retained",
        "pass_t_s",
        "pass_lap",
        "time_to_pass_s",
        "overtake_confidence",
        "overtake_reason",
        "quick_reversal",
        "reversal_t_s",
        "eligible",
        "exclusion_reason",
        "confidence",
        "pressure_gap_threshold_s",
        "minimum_pressure_s",
        "methodology_version",
    },
    ("marts", "racecraft_driver_summary"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "driver_name",
        "team",
        "attacking_opportunities",
        "converted_opportunities",
        "attacks_defended",
        "attack_conversion_pct",
        "attack_conversion_p05_pct",
        "attack_conversion_p95_pct",
        "attack_pressure_s",
        "distinct_defenders",
        "median_time_to_pass_s",
        "defensive_opportunities",
        "defences_held",
        "passes_conceded",
        "defence_hold_pct",
        "defence_hold_p05_pct",
        "defence_hold_p95_pct",
        "defensive_pressure_s",
        "distinct_attackers",
        "interrupted_attacks",
        "unresolved_attacks",
        "interrupted_defences",
        "unresolved_defences",
        "quick_reversals_made",
        "quick_reversals_conceded",
        "longest_battle_s",
        "offense_eligible",
        "defense_eligible",
        "offense_exclusion_reason",
        "defense_exclusion_reason",
        "offense_confidence",
        "defense_confidence",
        "confidence",
        "methodology_version",
    },
    ("marts", "mart_race_story"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "finish_position",
        "is_classified",
        "pace_samples",
        "controlled_pace_delta_sec",
        "pace_rank",
        "outcome_vs_pace",
        "story_label",
        "methodology_version",
    },
    ("marts", "mart_adjusted_stint_degradation"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "stint",
        "compound",
        "comparable_laps",
        "stint_length",
        "adjusted_deg_sec_per_lap",
        "raw_deg_sec_per_lap",
        "late_stint_loss_sec",
        "cliff_signal",
    },
    ("marts", "driver_track_archetypes"): {
        "speed_high_kph",
        "brake_high_pct",
        "low_speed_high_pct",
        "season",
        "round",
        "race_name",
        "circuit_archetype",
        "average_speed_kph",
        "braking_density_pct",
        "full_throttle_pct",
        "low_speed_segment_pct",
        "segments",
        "confidence",
        "methodology_version",
    },
    ("marts", "driver_track_fit"): {
        "median_gain_lo",
        "median_gain_hi",
        "interval_eligible",
        "driver_code",
        "driver_name",
        "circuit_archetype",
        "n_races",
        "median_gain_sec",
        "mean_gain_sec",
        "gain_direction_agreement_pct",
        "confidence",
        "methodology_version",
    },
    ("marts", "driver_dna_stability"): {
        "from_season",
        "to_season",
        "driver_code",
        "driver_name",
        "metric",
        "n_races",
        "full_estimate",
        "early_estimate",
        "late_estimate",
        "split_delta",
        "leave_one_out_max_delta",
        "sign_agreement_pct",
        "stable",
        "methodology_version",
    },
}

REQUIRED_TABLES = tuple(DASHBOARD_CONTRACT)


@dataclass(frozen=True)
class SnapshotManifest:
    """Metadata shipped next to one immutable dashboard database."""

    version: str
    generated_at: str
    source: str
    database_file: str
    sha256: str
    size_bytes: int
    latest_event_date: str | None
    table_rows: dict[str, int]
    schema_version: int = 2
    git_sha: str | None = None
    package_versions: dict[str, str] = field(default_factory=dict)
    methodology_versions: dict[str, list[str]] = field(default_factory=dict)
    coverage_exceptions: list[dict[str, Any]] = field(default_factory=list)


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _scalar(connection: duckdb.DuckDBPyConnection, query: str) -> Any:
    row = connection.execute(query).fetchone()
    if row is None:
        raise ValueError(f"snapshot query returned no row: {query}")
    return row[0]


def _version(now: dt.datetime) -> str:
    revision = os.getenv("GITHUB_SHA", "local")[:8]
    return f"{now:%Y%m%dT%H%M%SZ}-{revision}"


def _git_sha() -> str | None:
    configured = os.getenv("GITHUB_SHA")
    if configured:
        return configured
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def _package_versions() -> dict[str, str]:
    packages = (
        "f1-data-analytics",
        "duckdb",
        "pandas",
        "pyarrow",
        "fastf1",
        "dbt-core",
        "dagster",
    )
    versions: dict[str, str] = {}
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            continue
    return versions


def _methodology_versions(path: Path) -> dict[str, list[str]]:
    connection = duckdb.connect(str(path), read_only=True)
    try:
        relations = connection.execute(
            "select table_schema, table_name from information_schema.columns "
            "where column_name = 'methodology_version' "
            "and table_schema in (?, ?, ?) order by table_schema, table_name",
            list(DASHBOARD_SCHEMAS),
        ).fetchall()
        result: dict[str, list[str]] = {}
        for schema, table in relations:
            qualified = f"{_quote(str(schema))}.{_quote(str(table))}"
            values = connection.execute(
                f"select distinct methodology_version from {qualified} "
                "where methodology_version is not null order by methodology_version"
            ).fetchall()
            result[f"{schema}.{table}"] = [str(row[0]) for row in values]
        return result
    finally:
        connection.close()


def _copy_duckdb(source: Path, target: Path) -> dict[str, int]:
    if not source.is_file():
        raise FileNotFoundError(f"DuckDB warehouse does not exist: {source}")
    source_sql = str(source.resolve()).replace("'", "''")
    connection = duckdb.connect(str(target))
    rows: dict[str, int] = {}
    try:
        # dbt views in the development warehouse are bound to its normal `f1`
        # catalog name. Attach under that name, then materialize every relation so
        # the snapshot remains valid regardless of its eventual filename.
        connection.execute(f"ATTACH '{source_sql}' AS f1 (READ_ONLY)")
        available = {
            (str(schema), str(table))
            for schema, table in connection.execute(
                "select table_schema, table_name from information_schema.tables "
                "where table_catalog = 'f1' and table_schema in (?, ?, ?)",
                list(DASHBOARD_SCHEMAS),
            ).fetchall()
        }
        missing = sorted(set(DASHBOARD_CONTRACT) - available - {("marts", "source_coverage")})
        if missing:
            raise ValueError(f"warehouse is missing dashboard contract tables: {missing}")
        for schema, table in sorted(DASHBOARD_CONTRACT):
            if table == "source_coverage" and (schema, table) not in available:
                continue
            connection.execute(f"create schema if not exists {_quote(schema)}")
            qualified = f"{_quote(schema)}.{_quote(table)}"
            connection.execute(f"create table {qualified} as select * from f1.{qualified}")
            rows[f"{schema}.{table}"] = int(
                _scalar(connection, f"select count(*) from {qualified}")
            )
        materialize_source_coverage(connection)
        rows["marts.source_coverage"] = int(
            _scalar(connection, "select count(*) from marts.source_coverage")
        )
        connection.execute("detach f1")
    finally:
        connection.close()
    return rows


def _copy_scoped_snapshot(base: Path, target: Path) -> dict[str, int]:
    """Migrate a verified publication and recompute ratings on its own evidence."""
    manifest = json.loads(base.with_suffix(".json").read_text(encoding="utf-8"))
    if _sha256(base) != manifest.get("sha256"):
        raise ValueError("Base snapshot checksum does not match its manifest")
    rows = _copy_duckdb(base, target)
    with duckdb.connect(str(target)) as connection:
        for schema, table in sorted(DASHBOARD_CONTRACT):
            if "season" not in DASHBOARD_CONTRACT[(schema, table)]:
                continue
            qualified = f"{_quote(schema)}.{_quote(table)}"
            connection.execute(
                f"delete from {qualified} where season not between ? and ?",
                [FIRST_SEASON, LAST_SEASON],
            )
        connection.execute("""create table staging.stg_drivers as
            select driver_id, max(driver_code) as driver_code,
                max(driver_name) as driver_name,
                max(driver_nationality) as nationality,
                min(season) as first_season, max(season) as last_season,
                count(*) as race_entries
            from staging.stg_results group by driver_id""")
    from analytics.pipeline import (
        build_driver_pace_profile,
        build_driver_ratings,
        build_driver_ratings_v2,
    )

    scoped_settings = Settings(warehouse="duckdb", duckdb_path=target)
    build_driver_ratings(settings=scoped_settings)
    build_driver_ratings_v2(settings=scoped_settings)
    build_driver_pace_profile(from_season=FIRST_SEASON, settings=scoped_settings)
    with duckdb.connect(str(target)) as connection:
        connection.execute("drop table staging.stg_drivers")
        for schema, table in sorted(DASHBOARD_CONTRACT):
            qualified = f"{_quote(schema)}.{_quote(table)}"
            rows[f"{schema}.{table}"] = int(
                _scalar(connection, f"select count(*) from {qualified}")
            )
    return rows


def _copy_postgres(settings: Settings, target: Path) -> dict[str, int]:
    engine = create_engine(settings.pg_dsn)
    target_connection = duckdb.connect(str(target))
    rows: dict[str, int] = {}
    try:
        inspector = inspect(engine)
        with engine.connect() as source_connection:
            for schema in DASHBOARD_SCHEMAS:
                target_connection.execute(f"create schema if not exists {_quote(schema)}")
                available = set(
                    set(inspector.get_table_names(schema=schema))
                    | set(inspector.get_view_names(schema=schema))
                )
                required = sorted(
                    table for table_schema, table in DASHBOARD_CONTRACT if table_schema == schema
                )
                missing = sorted(set(required) - available - {"source_coverage"})
                if missing:
                    raise ValueError(
                        f"warehouse is missing dashboard contract tables in {schema}: {missing}"
                    )
                for table_name in required:
                    if table_name == "source_coverage" and table_name not in available:
                        continue
                    qualified = f"{_quote(schema)}.{_quote(table_name)}"
                    count = 0
                    first = True
                    query = text(f"select * from {qualified}")
                    for frame in pd.read_sql_query(query, source_connection, chunksize=50_000):
                        target_connection.register("snapshot_chunk", frame)
                        if first:
                            target_connection.execute(
                                f"create table {qualified} as select * from snapshot_chunk"
                            )
                            first = False
                        elif not frame.empty:
                            target_connection.execute(
                                f"insert into {qualified} by name select * from snapshot_chunk"
                            )
                        count += len(frame)
                        target_connection.unregister("snapshot_chunk")
                    rows[f"{schema}.{table_name}"] = count
        materialize_source_coverage(target_connection)
        rows["marts.source_coverage"] = int(
            _scalar(target_connection, "select count(*) from marts.source_coverage")
        )
    finally:
        target_connection.close()
        engine.dispose()
    return rows


def validate_recorded_story(connection: duckdb.DuckDBPyConnection) -> None:
    """Reject the retired analytical story even when its schema still compiles."""
    classification = connection.execute("""
        select count(*) from staging.stg_results
        where is_classified is distinct from case
            when finish_position > 0
                and trim(position_text) = cast(finish_position as varchar) then true
            when trim(position_text) in ('R', 'D', 'W', 'F') then false
            else null end
    """).fetchone()
    assert classification is not None
    if classification[0]:
        raise ValueError("Result classification disagrees with source position_text")
    violations = connection.execute("""
        select count(*) from marts.mart_race_story
        where methodology_version is distinct from 'recorded-results-v1'
            or pace_samples is distinct from 0
            or controlled_pace_delta_sec is not null
            or pace_rank is not null or outcome_vs_pace is not null
            or story_label is distinct from 'Recorded result; pace supplied by separate analysis'
    """).fetchone()
    assert violations is not None
    if violations[0]:
        raise ValueError("Retired race-story analysis must be rebuilt as recorded results")
    mismatch = connection.execute("""
        with expected as (
            select * from staging.stg_results r
            where exists (select 1 from marts.mart_lap_times l
                where l.season=r.season and l.round=r.round)
        )
        select count(*) from expected e full outer join marts.mart_race_story s
            using (season, round, driver_code)
        where e.driver_code is null or s.driver_code is null
            or e.finish_position is distinct from s.finish_position
            or e.is_classified is distinct from s.is_classified
    """).fetchone()
    duplicates = connection.execute("""
        select count(*) from (
            select season, round, driver_code from marts.mart_race_story
            group by season, round, driver_code having count(*) != 1
        )
    """).fetchone()
    assert mismatch is not None and duplicates is not None
    if mismatch[0] or duplicates[0]:
        raise ValueError("Recorded race story does not match loaded race results")


def validate_dashboard_snapshot(path: Path) -> str | None:
    """Validate that a snapshot can compile every public dashboard source."""
    connection = duckdb.connect(str(path), read_only=True)
    try:
        available = {
            (str(schema), str(table))
            for schema, table in connection.execute(
                "select table_schema, table_name from information_schema.tables"
            ).fetchall()
        }
        missing = sorted(set(REQUIRED_TABLES) - available)
        if missing:
            raise ValueError(f"dashboard snapshot is missing required tables: {missing}")
        broken_columns: list[str] = []
        for (schema, table), required in DASHBOARD_CONTRACT.items():
            columns = {
                str(row[0])
                for row in connection.execute(
                    "select column_name from information_schema.columns "
                    "where table_schema = ? and table_name = ?",
                    [schema, table],
                ).fetchall()
            }
            missing_columns = sorted(required - columns)
            if missing_columns:
                broken_columns.append(f"{schema}.{table}: {missing_columns}")
        if broken_columns:
            raise ValueError(
                "dashboard snapshot has incompatible columns: " + "; ".join(broken_columns)
            )
        for schema, table in sorted(DASHBOARD_CONTRACT):
            if "season" not in DASHBOARD_CONTRACT[(schema, table)]:
                continue
            qualified = f"{_quote(schema)}.{_quote(table)}"
            outside = connection.execute(
                f"select count(*) from {qualified} where season not between ? and ?",
                [FIRST_SEASON, LAST_SEASON],
            ).fetchone()
            if outside and outside[0]:
                raise ValueError(f"{schema}.{table} contains seasons outside 2024-2026")
        validate_recorded_story(connection)
        validate_source_coverage(connection)
        validate_snapshot_processing(connection)
        if _scalar(connection, "select count(*) from marts.driver_ratings") == 0:
            raise ValueError("dashboard snapshot contains no driver ratings")
        value = _scalar(
            connection,
            "select coalesce("
            "(select max(races.race_date) from staging.stg_races as races "
            "join (select distinct season, round from marts.mart_lap_times) as represented "
            "using (season, round)), "
            "(select max(race_date) from staging.stg_races)"
            ")",
        )
        return None if value is None else str(value)
    finally:
        connection.close()


def _write_snapshot_metadata(
    path: Path,
    *,
    version: str,
    generated_at: dt.datetime,
    source: str,
    latest_event_date: str | None,
    git_sha: str | None,
    package_versions: dict[str, str],
    methodology_versions: dict[str, list[str]],
) -> None:
    connection = duckdb.connect(str(path))
    try:
        connection.execute("create schema if not exists dashboard")
        connection.execute(
            "create table dashboard.snapshot_metadata as "
            "select ?::varchar as version, ?::timestamptz as generated_at, "
            "?::varchar as source, ?::date as latest_event_date, "
            "2::integer as schema_version, ?::varchar as git_sha, "
            "?::json as package_versions, ?::json as methodology_versions",
            [
                version,
                generated_at,
                source,
                latest_event_date,
                git_sha,
                json.dumps(package_versions, sort_keys=True),
                json.dumps(methodology_versions, sort_keys=True),
            ],
        )
    finally:
        connection.close()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.")
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json(payload: dict[str, Any], target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, target)


def _publish(path: Path, manifest_path: Path, publish_uri: str, version: str) -> None:
    import fsspec

    base = publish_uri.rstrip("/")
    filesystem, root = fsspec.core.url_to_fs(base)
    version_root = f"{root.rstrip('/')}/{version}"
    filesystem.makedirs(version_root, exist_ok=True)
    filesystem.put(str(path), f"{version_root}/{path.name}")
    filesystem.put(str(manifest_path), f"{version_root}/{manifest_path.name}")
    filesystem.put(str(manifest_path), f"{root.rstrip('/')}/latest.json")


def build_dashboard_snapshot(
    output_dir: Path,
    *,
    settings: Settings | None = None,
    version: str | None = None,
    publish_uri: str | None = None,
    now: dt.datetime | None = None,
    coverage_exceptions: list[dict[str, Any]] | None = None,
    base_snapshot: Path | None = None,
) -> SnapshotManifest:
    """Build, validate and atomically publish one versioned dashboard snapshot."""
    settings = settings or get_settings()
    now = now or dt.datetime.now(dt.UTC)
    version = version or _version(now)
    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / f"f1-dashboard-{version}.duckdb"
    if final_path.exists():
        raise FileExistsError(f"snapshot version already exists: {version}")

    descriptor, temporary_name = tempfile.mkstemp(
        dir=output_dir, prefix=f".{version}.", suffix=".duckdb"
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    temporary.unlink()
    try:
        if base_snapshot is not None:
            if settings.warehouse != "duckdb":
                raise ValueError("Snapshot migration requires a DuckDB warehouse")
            table_rows = _copy_scoped_snapshot(base_snapshot, temporary)
        else:
            table_rows = (
                _copy_duckdb(settings.duckdb_path, temporary)
                if settings.warehouse == "duckdb"
                else _copy_postgres(settings, temporary)
            )
        latest_event_date = validate_dashboard_snapshot(temporary)
        validate_partition_preservation(
            output_dir / "latest.duckdb", temporary, coverage_exceptions
        )
        git_sha = _git_sha()
        package_versions = _package_versions()
        methodology_versions = _methodology_versions(temporary)
        _write_snapshot_metadata(
            temporary,
            version=version,
            generated_at=now,
            source="scoped_snapshot" if base_snapshot is not None else settings.warehouse,
            latest_event_date=latest_event_date,
            git_sha=git_sha,
            package_versions=package_versions,
            methodology_versions=methodology_versions,
        )
        os.replace(temporary, final_path)
    finally:
        temporary.unlink(missing_ok=True)

    manifest = SnapshotManifest(
        version=version,
        generated_at=now.isoformat(),
        source="scoped_snapshot" if base_snapshot is not None else settings.warehouse,
        database_file=final_path.name,
        sha256=_sha256(final_path),
        size_bytes=final_path.stat().st_size,
        latest_event_date=latest_event_date,
        table_rows=table_rows,
        git_sha=git_sha,
        package_versions=package_versions,
        methodology_versions=methodology_versions,
        coverage_exceptions=coverage_exceptions or [],
    )
    manifest_path = output_dir / f"f1-dashboard-{version}.json"
    _write_json(asdict(manifest), manifest_path)
    _atomic_copy(final_path, output_dir / "latest.duckdb")
    _write_json(asdict(manifest), output_dir / "latest.json")
    if publish_uri:
        _publish(final_path, manifest_path, publish_uri, version)
    return manifest


def fetch_dashboard_snapshot(uri: str, output: Path) -> SnapshotManifest:
    """Resolve ``latest.json``, verify its immutable database and install it locally."""
    import fsspec

    base = uri.rstrip("/")
    filesystem, root = fsspec.core.url_to_fs(base)
    with filesystem.open(f"{root.rstrip('/')}/latest.json", "rb") as handle:
        payload = json.load(handle)
    manifest = SnapshotManifest(**payload)
    remote = f"{root.rstrip('/')}/{manifest.version}/{manifest.database_file}"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    try:
        filesystem.get(remote, str(temporary))
        if _sha256(temporary) != manifest.sha256:
            raise ValueError("downloaded dashboard snapshot checksum does not match its manifest")
        validate_dashboard_snapshot(temporary)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    _write_json(asdict(manifest), output.with_suffix(".json"))
    return manifest
