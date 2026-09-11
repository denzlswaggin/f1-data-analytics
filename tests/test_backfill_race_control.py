import sys

import pandas as pd
from analytics.replay import IncompleteReplayError
from scripts import backfill_race_control


def test_backfill_reuses_inputs_and_keeps_incomplete_replay_excluded(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(sys, "argv", ["backfill_race_control.py"])
    monkeypatch.setattr(backfill_race_control, "get_settings", lambda: None)

    def query(sql, settings):
        if "staging.stg_results" in sql:
            return pd.DataFrame({"season": [2024, 2025, 2026], "round": [1, 1, 1]})
        # 2024 already has all inputs and a replay; 2025 has only messages.
        present = "season = 2024" in sql or ("season = 2025" in sql and "stg_race_control" in sql)
        return pd.DataFrame({"n": [int(present)]})

    monkeypatch.setattr(backfill_race_control, "read_query", query)
    monkeypatch.setattr(
        backfill_race_control,
        "ingest_race_control",
        lambda season, rounds, **kwargs: calls.append(("messages", season)),
    )
    monkeypatch.setattr(
        backfill_race_control,
        "ingest_positions",
        lambda season, rounds, **kwargs: calls.append(("positions", season)),
    )

    def replay(season, rnd, **kwargs):
        calls.append(("replay", season))
        if season == 2026:
            raise IncompleteReplayError("Incomplete position feed")

    monkeypatch.setattr(backfill_race_control, "build_race_replay_incremental", replay)
    monkeypatch.setattr(
        backfill_race_control,
        "build_race_control_impact_incremental",
        lambda season, rnd, **kwargs: calls.append(("impact", season)),
    )
    backfill_race_control.main()

    assert calls == [
        ("impact", 2024),
        ("positions", 2025),
        ("replay", 2025),
        ("impact", 2025),
        ("messages", 2026),
        ("positions", 2026),
        ("replay", 2026),
        ("impact", 2026),
    ]
    assert "Incomplete position feed" in capsys.readouterr().out
