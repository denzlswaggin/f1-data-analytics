"""Tests for observed racecraft battle conversion."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import duckdb
import pandas as pd
import pytest
from analytics.pipeline import (
    build_all_racecraft_battles,
    build_racecraft_battles,
    build_racecraft_battles_incremental,
)
from analytics.racecraft import RacecraftResult, analyse_racecraft_battles
from ingestion.config import Settings
from ingestion.loaders.warehouse import read_query


def _replay(
    end_t: int,
    *,
    order: Callable[[int], tuple[str, str, str]] | None = None,
    gap: Callable[[int], float] | None = None,
    status: Callable[[int], str] | None = None,
    pit: Callable[[int, str], bool] | None = None,
    defender_lap: int = 2,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    order = order or (lambda _: ("B", "A", "C"))
    gap = gap or (lambda _: 0.8)
    status = status or (lambda _: "1")
    pit = pit or (lambda _t, _driver: False)
    for t_s in range(60, end_t + 1):
        running = order(t_s)
        for position, driver in enumerate(running, start=1):
            lap_number = defender_lap if driver == "B" else 2
            rows.append(
                {
                    "season": 2026,
                    "round": 1,
                    "race_name": "Test Grand Prix",
                    "driver_code": driver,
                    "driver_name": f"Driver {driver}",
                    "team": f"Team {driver}",
                    "t_s": float(t_s),
                    "lap_number": lap_number,
                    "lap_progress": 0.10 + (t_s - 60) / 1000,
                    "stint": 1,
                    "running_order": position,
                    "gap_to_ahead_s": float("nan")
                    if position == 1
                    else gap(t_s)
                    if driver == "A"
                    else 4.0,
                    "track_status": status(t_s),
                    "is_pit_boundary": pit(t_s, driver),
                }
            )
    return pd.DataFrame(rows)


def _overtakes(*rows: tuple[float, str, str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "season": 2026,
                "round": 1,
                "t_s": t_s,
                "passer_code": passer,
                "passed_code": passed,
                "confidence": 0.95,
                "reason": "stable_order_change",
            }
            for t_s, passer, passed in rows
        ],
        columns=[
            "season",
            "round",
            "t_s",
            "passer_code",
            "passed_code",
            "confidence",
            "reason",
        ],
    )


def _battle(result: RacecraftResult, attacker: str = "A") -> pd.Series:
    battles = result.battles
    return battles.loc[battles["attacker_code"].eq(attacker)].iloc[0]


def test_matches_pass_when_attacker_moves_into_lead() -> None:
    replay = _replay(
        72,
        order=lambda t: ("B", "A", "C") if t < 70 else ("A", "B", "C"),
    )

    result = analyse_racecraft_battles(replay, _overtakes((70, "A", "B")))
    battle = _battle(result)

    assert battle["outcome"] == "Converted"
    assert battle["eligible"]
    assert battle["pressure_seconds"] == pytest.approx(10.0)
    assert battle["pass_t_s"] == pytest.approx(70.0)
    assert battle["coverage_pct"] == pytest.approx(100.0)


def test_clean_sustained_gap_release_is_defended() -> None:
    replay = _replay(85, gap=lambda t: 0.8 if t < 70 else 2.5)

    battle = _battle(analyse_racecraft_battles(replay, _overtakes()))

    assert battle["outcome"] == "Defended"
    assert battle["defender_retained"]
    assert battle["eligible"]
    assert battle["valid_samples"] == 26
    assert battle["contact_seconds"] == pytest.approx(10.0)


@pytest.mark.parametrize(
    ("status", "pit", "reason"),
    [
        (lambda t: "4" if t == 70 else "1", None, "non_green"),
        (None, lambda t, driver: t == 70 and driver == "A", "pit_boundary"),
    ],
)
def test_interruption_is_never_counted_as_a_defence(
    status: Callable[[int], str] | None,
    pit: Callable[[int, str], bool] | None,
    reason: str,
) -> None:
    replay = _replay(70, status=status, pit=pit)

    battle = _battle(analyse_racecraft_battles(replay, _overtakes()))

    assert battle["outcome"] == "Interrupted"
    assert battle["terminal_reason"] == reason
    assert not battle["eligible"]
    assert not battle["defender_retained"]


def test_directional_pass_must_be_within_three_seconds() -> None:
    replay = _replay(
        73,
        order=lambda t: ("B", "A", "C") if t < 70 else ("A", "B", "C"),
    )

    battle = _battle(analyse_racecraft_battles(replay, _overtakes((73, "A", "B"))))

    assert battle["outcome"] == "Interrupted"
    assert not battle["converted"]


def test_flags_a_reverse_pass_within_sixty_seconds() -> None:
    replay = _replay(
        72,
        order=lambda t: ("B", "A", "C") if t < 70 else ("A", "B", "C"),
    )

    battle = _battle(
        analyse_racecraft_battles(
            replay,
            _overtakes((70, "A", "B"), (100, "B", "A")),
        )
    )

    assert battle["quick_reversal"]
    assert battle["reversal_t_s"] == pytest.approx(100.0)


def test_reversal_is_made_by_original_defender_and_conceded_by_original_attacker() -> None:
    replay = _replay(72, order=lambda t: ("B", "A", "C") if t < 70 else ("A", "B", "C"))
    result = analyse_racecraft_battles(replay, _overtakes((70, "A", "B"), (100, "B", "A")))
    summary = result.summary.set_index("driver_code")
    assert summary.loc["B", "quick_reversals_made"] == 1
    assert summary.loc["B", "quick_reversals_conceded"] == 0
    assert summary.loc["A", "quick_reversals_made"] == 0
    assert summary.loc["A", "quick_reversals_conceded"] == 1
    assert summary["quick_reversals_made"].sum() == summary["quick_reversals_conceded"].sum() == 1


@pytest.mark.parametrize("interruption", [1.8, 2.0, 0.0, -1.0, float("nan"), float("inf")])
def test_release_must_restart_after_neutral_invalid_or_missing_gap(interruption: float) -> None:
    def gap(t: int) -> float:
        return 0.8 if t < 70 else interruption if 71 <= t <= 84 else 2.5

    short = _battle(analyse_racecraft_battles(_replay(85, gap=gap), _overtakes()))
    assert short["outcome"] == "Unresolved"
    assert not short["defender_retained"]
    assert short["release_run_s"] == 0
    recovered = _battle(analyse_racecraft_battles(_replay(100, gap=gap), _overtakes()))
    assert recovered["outcome"] == "Defended"
    assert recovered["end_t_s"] == 100
    assert recovered["release_run_s"] == 15


@pytest.mark.parametrize("interruption", [1.2, 1.8, 0.0, float("nan")])
def test_fragmented_pressure_cannot_qualify_as_ten_continuous_seconds(interruption: float) -> None:
    replay = _replay(
        72,
        gap=lambda t: interruption if t == 65 else 0.8,
        order=lambda t: ("B", "A", "C") if t < 71 else ("A", "B", "C"),
    )
    battle = _battle(analyse_racecraft_battles(replay, _overtakes((71, "A", "B"))))
    assert battle["converted"]
    assert battle["pressure_seconds"] == 10
    assert battle["longest_pressure_run_s"] == 5
    assert not battle["eligible"]
    assert battle["exclusion_reason"] == "insufficient_sustained_pressure"


def test_missing_nominal_pressure_tick_resets_run_even_when_episode_survives() -> None:
    replay = _replay(72, order=lambda t: ("B", "A", "C") if t < 71 else ("A", "B", "C"))
    replay = replay.loc[~replay.t_s.eq(65)]
    battle = _battle(analyse_racecraft_battles(replay, _overtakes((71, "A", "B"))))
    assert battle["pressure_seconds"] == 10
    assert battle["longest_pressure_run_s"] == 5
    assert battle["coverage_pct"] > 80
    assert not battle["eligible"]


@pytest.mark.parametrize("kind", ["missing_tick", "lap_mismatch"])
def test_release_restarts_after_missing_tick_or_lap_mismatch(kind: str) -> None:
    def run(end: int) -> pd.Series:
        replay = _replay(end, gap=lambda t: 0.8 if t < 70 else 2.5)
        if kind == "missing_tick":
            replay = replay.loc[~replay.t_s.eq(75)]
        else:
            replay.loc[replay.t_s.eq(75) & replay.driver_code.eq("B"), "lap_number"] = 3
        return _battle(analyse_racecraft_battles(replay, _overtakes()))

    assert run(85)["outcome"] == "Unresolved"
    assert run(85)["release_run_s"] == 9
    assert run(91)["outcome"] == "Defended"
    assert run(91)["release_run_s"] == 15


def test_high_confidence_uses_continuous_not_total_pressure() -> None:
    replay = _replay(100, gap=lambda t: 1.2 if t == 72 else 0.8 if t < 85 else 2.5)
    battle = _battle(analyse_racecraft_battles(replay, _overtakes()))
    assert battle["pressure_seconds"] == 24
    assert battle["longest_pressure_run_s"] == 12
    assert battle["eligible"]
    assert battle["confidence"] == "medium"


def test_lap_mismatch_breaks_continuous_pressure() -> None:
    replay = _replay(70)
    replay.loc[replay.t_s.eq(65) & replay.driver_code.eq("B"), "lap_number"] = 3
    battle = _battle(analyse_racecraft_battles(replay, _overtakes((71, "A", "B"))))
    assert battle["pressure_seconds"] == 10
    assert battle["longest_pressure_run_s"] == 5
    assert not battle["eligible"]


def test_two_second_cadence_uses_sample_supported_pressure_and_elapsed_release() -> None:
    replay = _replay(86, gap=lambda t: 0.8 if t < 70 else 2.5)
    replay = replay.loc[replay.t_s.mod(2).eq(0)]
    battle = _battle(analyse_racecraft_battles(replay, _overtakes()))
    assert battle["pressure_seconds"] == 10
    assert battle["longest_pressure_run_s"] == 10
    assert battle["release_run_s"] == 16
    assert battle["outcome"] == "Defended"
    assert battle["eligible"]


def test_missing_track_status_interrupts_instead_of_confirming_release() -> None:
    replay = _replay(90, gap=lambda t: 0.8 if t < 70 else 2.5)
    replay.loc[replay.t_s.eq(75) & replay.driver_code.eq("B"), "track_status"] = None
    battle = _battle(analyse_racecraft_battles(replay, _overtakes()))
    assert battle["outcome"] == "Interrupted"
    assert not battle["eligible"]


def test_release_requires_fifteen_elapsed_seconds_not_fifteen_samples() -> None:
    def run(end: int) -> pd.Series:
        return _battle(
            analyse_racecraft_battles(
                _replay(end, gap=lambda t: 0.8 if t < 70 else 2.5), _overtakes()
            )
        )

    assert run(84)["outcome"] == "Unresolved"
    assert run(84)["release_run_s"] == 14
    assert run(85)["outcome"] == "Defended"
    assert run(85)["longest_pressure_run_s"] == 10


def test_rate_is_only_published_after_five_eligible_opportunities() -> None:
    def gap(t_s: int) -> float:
        return 0.8 if (t_s - 60) % 30 < 10 else 2.5

    result = analyse_racecraft_battles(_replay(205, gap=gap), _overtakes())
    attacker = result.summary.loc[result.summary["driver_code"].eq("A")].iloc[0]
    defender = result.summary.loc[result.summary["driver_code"].eq("B")].iloc[0]

    assert attacker["attacking_opportunities"] == 5
    assert attacker["attack_conversion_pct"] == pytest.approx(0.0)
    assert defender["defensive_opportunities"] == 5
    assert defender["defence_hold_pct"] == pytest.approx(100.0)
    assert defender["defence_hold_p05_pct"] < defender["defence_hold_pct"]


def test_lapped_car_is_not_treated_as_direct_battle() -> None:
    result = analyse_racecraft_battles(_replay(75, defender_lap=3), _overtakes())

    assert result.battles.empty
    assert len(result.summary) == 3


def test_short_pressure_is_retained_but_ineligible() -> None:
    replay = _replay(
        68,
        order=lambda t: ("B", "A", "C") if t < 65 else ("A", "B", "C"),
    )

    battle = _battle(analyse_racecraft_battles(replay, _overtakes((65, "A", "B"))))

    assert battle["outcome"] == "Converted"
    assert not battle["eligible"]
    assert battle["exclusion_reason"] == "insufficient_sustained_pressure"


def test_output_is_deterministic_for_unsorted_duplicate_replay_ticks() -> None:
    replay = _replay(72, gap=lambda t: 0.8 if t < 70 else 2.5)
    noisy = pd.concat([replay.sample(frac=1, random_state=7), replay.iloc[[0]]])

    first = analyse_racecraft_battles(replay, _overtakes()).battles
    second = analyse_racecraft_battles(noisy, _overtakes()).battles

    pd.testing.assert_frame_equal(first, second)


def test_empty_input_preserves_typed_contract() -> None:
    replay = _replay(60).iloc[0:0]

    result = analyse_racecraft_battles(replay, _overtakes())

    assert result.battles.empty
    assert result.summary.empty
    assert str(result.battles["eligible"].dtype) == "boolean"
    assert str(result.battles["season"].dtype) == "Int64"
    assert str(result.summary["attack_conversion_pct"].dtype) == "float64"


def test_rejects_duplicate_directional_pass_rows() -> None:
    passes = _overtakes((70, "A", "B"), (70, "A", "B"))

    with pytest.raises(ValueError, match="duplicate directional pass"):
        analyse_racecraft_battles(_replay(70), passes)


def _seed_warehouse(path: Path) -> Settings:
    replay = _replay(85, gap=lambda t: 0.8 if t < 70 else 2.5)
    second = replay.assign(round=2, race_name="Second Grand Prix")
    replay = pd.concat([replay, second], ignore_index=True)
    replay["x"] = replay["t_s"]
    replay["y"] = 0.0
    lap_rows = (
        replay[["season", "round", "driver_code", "lap_number", "stint", "team", "track_status"]]
        .drop_duplicates(["season", "round", "driver_code", "lap_number"])
        .assign(session="R", compound="MEDIUM", tyre_life=5)
    )
    races = pd.DataFrame(
        [
            {"season": 2026, "round": 1, "race_name": "Test Grand Prix"},
            {"season": 2026, "round": 2, "race_name": "Second Grand Prix"},
        ]
    )
    codes = replay[["season", "driver_code", "driver_name"]].drop_duplicates()
    connection = duckdb.connect(str(path))
    try:
        connection.execute("create schema staging")
        connection.execute("create schema marts")
        for table, frame in {
            "staging.stg_laps": lap_rows,
            "staging.stg_races": races,
            "staging.stg_driver_codes": codes,
            "marts.race_replay": replay.drop(columns=["race_name", "driver_name", "team"]),
            "marts.race_overtakes": _overtakes(),
        }.items():
            connection.register("source_frame", frame)
            connection.execute(f"create table {table} as select * from source_frame")
            connection.unregister("source_frame")
    finally:
        connection.close()
    return Settings(duckdb_path=path)


def test_pipeline_materialises_all_and_replaces_one_partition(tmp_path: Path) -> None:
    settings = _seed_warehouse(tmp_path / "racecraft.duckdb")

    all_result = build_all_racecraft_battles(settings)
    build_racecraft_battles(2026, 1, settings)
    incremental = build_racecraft_battles_incremental(2026, 1, settings)
    persisted = read_query(
        "select season, round, outcome from marts.racecraft_battles order by round",
        settings,
    )
    summaries = read_query("select * from marts.racecraft_driver_summary", settings)

    assert len(all_result.battles) == 2
    assert len(incremental.battles) == 1
    assert persisted["round"].tolist() == [1, 2]
    assert set(persisted["outcome"]) == {"Defended"}
    assert len(summaries) == 6
    pd.testing.assert_frame_equal(
        all_result.battles.loc[all_result.battles["round"].eq(1)].reset_index(drop=True),
        incremental.battles.reset_index(drop=True),
    )


def _source_sql(name: str) -> str:
    return (Path(__file__).parents[1] / "dashboard/sources/f1" / f"{name}.sql").read_text(
        encoding="utf-8"
    )


def test_season_profiles_pool_counts_pressure_opponents_and_intervals(tmp_path: Path) -> None:
    from analytics.racecraft import _wilson
    from ingestion.loaders.warehouse import replace_table

    settings = _seed_warehouse(tmp_path / "profiles.duckdb")
    result = build_all_racecraft_battles(settings)
    template = result.battles.iloc[0].to_dict()
    rows = []
    # One success in round 1, two successes and three holds in round 2.
    # The season is 3/6, not the unweighted mean of 100% and 40%.
    for index in range(7):
        success = index < 3
        rows.append(
            {
                **template,
                "battle_id": f"battle-{index}",
                "round": 1 if index == 0 else 2,
                "converted": success,
                "defender_retained": not success and index < 6,
                "outcome": "Converted" if success else "Defended" if index < 6 else "Interrupted",
                "eligible": index < 6,
                "pressure_seconds": 12.0,
                "time_to_pass_s": [100.0, 10.0, 20.0][index] if success else float("nan"),
            }
        )
    replace_table(pd.DataFrame(rows), "marts", "racecraft_battles", settings)
    profiles = read_query(_source_sql("racecraft_profiles"), settings)
    season = profiles.loc[(profiles["round"] == 0) & (profiles["driver_code"] == "A")].iloc[0]
    assert season["attacking_opportunities"] == 6
    assert season["converted_opportunities"] == 3
    assert season["attack_conversion_pct"] == 50
    lower, upper = _wilson(3, 6)
    assert season["attack_conversion_p05_pct"] == pytest.approx(lower)
    assert season["attack_conversion_p95_pct"] == pytest.approx(upper)
    assert season["observed_attack_pressure_s"] == 84
    assert season["observed_attacks"] == 7
    assert season["distinct_defenders"] == 1
    assert season["median_time_to_pass_s"] == 20
    assert season["races_covered"] == 2
    round_one = profiles.loc[(profiles["round"] == 1) & (profiles["driver_code"] == "A")].iloc[0]
    assert not round_one["offense_eligible"]
    assert pd.isna(round_one["attack_conversion_pct"])
    round_two = profiles.loc[(profiles["round"] == 2) & (profiles["driver_code"] == "A")].iloc[0]
    assert round_two["offense_eligible"]
    assert round_two["attack_conversion_pct"] == 40
    defender = profiles.loc[(profiles["round"] == 0) & (profiles["driver_code"] == "B")].iloc[0]
    assert defender["defensive_opportunities"] == 6
    assert defender["defences_held"] == 3
    assert defender["interrupted_defences"] == 1
    zero = profiles.loc[(profiles["round"] == 0) & (profiles["driver_code"] == "C")].iloc[0]
    assert zero["observed_attacks"] == 0
    assert zero["observed_defensive_pressure_s"] == 0
    assert pd.isna(zero["defence_hold_pct"])


def test_export_uses_each_drivers_start_lap_and_never_duplicates_episodes(tmp_path: Path) -> None:
    settings = _seed_warehouse(tmp_path / "tyres.duckdb")
    build_all_racecraft_battles(settings)
    with duckdb.connect(str(settings.duckdb_path)) as connection:
        connection.execute("update staging.stg_laps set tyre_life=10 where driver_code='A'")
        # The leading car has crossed the timing line before the attacker.
        connection.execute("update marts.race_replay set lap_number=3 where driver_code='B'")
        connection.execute(
            "update staging.stg_laps set lap_number=3, tyre_life=4, compound='HARD' where driver_code='B'"
        )
        exported = connection.execute(_source_sql("racecraft_battles")).fetchdf()
        assert len(exported) == 2
        assert exported["attacker_tyre_age_laps"].tolist() == [10, 10]
        assert exported["defender_compound"].tolist() == ["HARD", "HARD"]
        assert exported["tyre_age_delta_laps"].tolist() == [6, 6]
        connection.execute(
            "insert into staging.stg_laps select * from staging.stg_laps where driver_code='A'"
        )
        connection.execute("delete from staging.stg_laps where driver_code='B'")
        ambiguous = connection.execute(_source_sql("racecraft_battles")).fetchdf()
        assert len(ambiguous) == 2
        assert ambiguous["attacker_compound"].isna().all()
        assert ambiguous["defender_tyre_age_laps"].isna().all()
        assert ambiguous["tyre_age_delta_laps"].isna().all()


def test_coverage_distinguishes_zero_battles_missing_processing_and_missing_order(
    tmp_path: Path,
) -> None:
    from scripts.check_dashboard_data import CHECKS

    settings = _seed_warehouse(tmp_path / "coverage.duckdb")
    build_all_racecraft_battles(settings)
    check = next(check for check in CHECKS if check.name == "racecraft driver coverage")
    with duckdb.connect(str(settings.duckdb_path)) as connection:

        def missing_count() -> int:
            row = connection.execute(check.query).fetchone()
            assert row is not None
            return int(row[0])

        assert missing_count() == 0
        connection.execute("delete from marts.racecraft_battles where round=1")
        connection.execute("delete from marts.racecraft_driver_summary where round=2")
        coverage = connection.execute(_source_sql("racecraft_coverage")).fetchdf()
        assert coverage["coverage_status"].tolist() == [
            "Processed: no observed battles",
            "Incomplete racecraft processing",
        ]
        assert missing_count() == 3
        connection.execute("update marts.race_replay set running_order=null where driver_code='C'")
        assert missing_count() == 2
        coverage = connection.execute(_source_sql("racecraft_coverage")).fetchdf()
        assert coverage["drivers_without_running_order"].tolist() == [1, 1]


def test_racecraft_rebuilds_passes_and_receipts_including_zero_event_races(tmp_path: Path) -> None:
    from analytics.racecraft_integrity import validate_snapshot_processing

    settings = _seed_warehouse(tmp_path / "processing.duckdb")
    with duckdb.connect(str(settings.duckdb_path)) as c:
        c.execute("""update marts.race_replay set running_order =
            case when driver_code = 'A' then 1 when driver_code = 'B' then 2 else 3 end,
            gap_to_ahead_s = case when driver_code = 'A' then null when driver_code = 'B' then 0.8 else 4 end
            where round = 1 and t_s >= 70""")
    result = build_all_racecraft_battles(settings)
    assert result.battles["converted"].sum() == 1
    with duckdb.connect(str(settings.duckdb_path)) as c:
        validate_snapshot_processing(c)
        assert c.execute(
            "select round, overtake_rows from marts.racecraft_processing order by round"
        ).fetchall() == [(1, 1), (2, 0)]
        c.execute("delete from marts.race_overtakes where round = 1")
        with pytest.raises(ValueError, match="Stale Racecraft overtakes"):
            validate_snapshot_processing(c)
    build_racecraft_battles(2026, 1, settings)
    with duckdb.connect(str(settings.duckdb_path)) as c:
        validate_snapshot_processing(c)
        c.execute("delete from marts.racecraft_processing where round = 2")
        with pytest.raises(ValueError, match="coverage mismatch"):
            validate_snapshot_processing(c)


@pytest.mark.parametrize(
    "mutation,part",
    [
        ("update marts.race_replay set x=x+1 where round=1", "replay"),
        ("update staging.stg_laps set track_status='2' where round=1", "laps"),
        ("update marts.pit_lap_context set is_pit_boundary=true where round=1", "pit_context"),
        ("update marts.racecraft_battles set confidence='low' where round=1", "battles"),
        (
            "update marts.racecraft_driver_summary set attacking_opportunities=99 where round=1",
            "summary",
        ),
    ],
)
def test_receipts_reject_changed_inputs_and_outputs(
    tmp_path: Path, mutation: str, part: str
) -> None:
    from analytics.racecraft_integrity import validate_snapshot_processing

    settings = _seed_warehouse(tmp_path / "stale.duckdb")
    build_all_racecraft_battles(settings)
    with duckdb.connect(str(settings.duckdb_path)) as c:
        validate_snapshot_processing(c)
        c.execute(mutation)
        with pytest.raises(ValueError, match=f"Stale Racecraft {part}"):
            validate_snapshot_processing(c)


def test_bundle_rolls_back_every_table_on_partition_failure(tmp_path: Path) -> None:
    from analytics.racecraft_integrity import validate_snapshot_processing
    from ingestion.loaders.warehouse import replace_mart_bundle

    settings = _seed_warehouse(tmp_path / "rollback.duckdb")
    build_all_racecraft_battles(settings)
    battles = read_query("select * from marts.racecraft_battles where round=1", settings)
    summaries = read_query("select * from marts.racecraft_driver_summary where round=1", settings)
    with pytest.raises(duckdb.Error):
        replace_mart_bundle(
            {
                "racecraft_battles": battles.iloc[0:0],
                "racecraft_driver_summary": summaries.rename(
                    columns={"driver_code": "invalid_column"}
                ),
            },
            settings,
            {"season": 2026, "round": 1},
        )
    with duckdb.connect(str(settings.duckdb_path)) as c:
        validate_snapshot_processing(c)


def test_fingerprints_ignore_order_and_numeric_storage_but_detect_value_changes() -> None:
    from analytics.racecraft_integrity import fingerprint

    a = pd.DataFrame({"driver": ["A", "B"], "n": pd.Series([1, None], dtype="Int64")})
    b = a.iloc[::-1].assign(n=lambda frame: frame.n.astype("float64"))
    assert fingerprint(a) == fingerprint(b)
    assert fingerprint(a) == fingerprint(a.astype({"n": object}))
    b.loc[0, "n"] = 1.1
    assert fingerprint(a) != fingerprint(b)
