"""Selection logic for the unattended round-level refresh."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
from ingestion.config import Settings
from ingestion.loaders.warehouse import load_dataframe
from ingestion.pipeline import latest_completed_round


def test_latest_completed_round_excludes_race_day(tmp_path: Path) -> None:
    settings = Settings(warehouse="duckdb", duckdb_path=tmp_path / "f1.duckdb")
    races = pd.DataFrame(
        {
            "season": [2026, 2026, 2026],
            "round": [1, 2, 3],
            "date": ["2026-03-08", "2026-03-15", "2026-03-22"],
        }
    )
    load_dataframe(races, "races", 2026, settings)

    assert latest_completed_round(2026, settings, as_of=dt.date(2026, 3, 15)) == 1
    assert latest_completed_round(2026, settings, as_of=dt.date(2026, 3, 16)) == 2


def test_latest_completed_round_handles_unbootstrapped_calendar(tmp_path: Path) -> None:
    settings = Settings(warehouse="duckdb", duckdb_path=tmp_path / "missing.duckdb")
    assert latest_completed_round(2026, settings, as_of=dt.date(2026, 3, 16)) is None
