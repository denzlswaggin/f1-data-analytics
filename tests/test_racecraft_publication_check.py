"""The publication checker rejects inconsistent battle evidence and rollups."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import duckdb
import pytest


def _snapshot(path: Path, mutation: str = "") -> None:
    with duckdb.connect(str(path)) as connection:
        connection.execute("create schema marts")
        connection.execute("""create table marts.racecraft_battles as
            select 2025 as season, 4 as round, 'A' as attacker_code, 'B' as defender_code,
                20.0 as longest_pressure_run_s, 20.0 as pressure_seconds,
                10.0 as minimum_pressure_s, true as eligible, 'high' as confidence,
                'Defended' as outcome, 15.0 as release_run_s, true as defender_retained,
                false as converted, false as quick_reversal, 'battle-1' as battle_id
            union all
            select 2025, 4, 'A', 'B', 20.0, 20.0, 10.0, true, 'high', 'Converted',
                0.0, false, true, true, 'battle-2'""")
        connection.execute("""create table marts.race_replay as
            select 2025 as season, 4 as round, 'A' as driver_code,
                1 as running_order, 100.0 as t_s
            union all select 2025, 4, 'B', 2, 100.0""")
        connection.execute("""create table marts.racecraft_driver_summary as
            select 2025 as season, 4 as round, 'A' as driver_code,
                0 as quick_reversals_made, 1 as quick_reversals_conceded,
                2 as attacking_opportunities, 0 as defensive_opportunities,
                1 as converted_opportunities, 0 as defences_held
            union all select 2025, 4, 'B', 1, 0, 0, 2, 0, 1""")
        if mutation:
            connection.execute(mutation)


def _run(path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "check_racecraft_battles.py"
    monkeypatch.setattr(sys, "argv", [str(script), str(path)])
    runpy.run_path(str(script), run_name="__main__")


def test_accepts_consistent_publication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "snapshot.duckdb"
    _snapshot(path)
    _run(path, monkeypatch)


@pytest.mark.parametrize(
    "mutation",
    [
        "update marts.racecraft_battles set longest_pressure_run_s = 5",
        "update marts.racecraft_battles set longest_pressure_run_s = 21",
        "update marts.racecraft_battles set longest_pressure_run_s = 15",
        "update marts.racecraft_battles set release_run_s = 14 where outcome = 'Defended'",
        "update marts.racecraft_battles set outcome = 'Interrupted'",
        "update marts.racecraft_driver_summary set quick_reversals_made = 0",
        "update marts.racecraft_driver_summary set quick_reversals_conceded = 0",
        "update marts.racecraft_driver_summary set attacking_opportunities = 0",
        "delete from marts.racecraft_driver_summary where driver_code = 'B'",
        "insert into marts.race_replay values (2025, 4, 'C', 3, 100.0)",
        "insert into marts.racecraft_driver_summary select * from marts.racecraft_driver_summary",
        "update marts.racecraft_battles set battle_id = 'duplicate'",
    ],
)
def test_rejects_inconsistent_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    path = tmp_path / "snapshot.duckdb"
    _snapshot(path, mutation)
    with pytest.raises(SystemExit, match="FAIL: racecraft publication rules"):
        _run(path, monkeypatch)
