"""Tests for observed racecraft battle conversion."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import duckdb
import pandas as pd
import pytest
from analytics.pipeline import (
    build_all_racecraft_battles,
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
    lap_rows = (
        replay[["season", "round", "driver_code", "lap_number", "stint", "team", "track_status"]]
        .drop_duplicates(["season", "round", "driver_code", "lap_number"])
        .assign(session="R")
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
