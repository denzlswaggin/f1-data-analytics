import json
import sys
from pathlib import Path

import pandas as pd
import pytest
from analytics.pit_timing import _empty_result
from scripts import backfill_pit_timing


def test_resume_preserves_baseline_and_rebuilds_only_remaining_races(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report = tmp_path / "coverage.json"
    baseline = [{"season": 2024, "round": 1, "eligible_stops": 0}]
    report.write_text(
        json.dumps(
            {
                "seasons": [2024, 2026],
                "before": baseline,
                "completed": [{"season": 2024, "round": 1}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["backfill", "--report", str(report), "--resume"])
    monkeypatch.setattr(backfill_pit_timing, "get_settings", lambda: None)
    monkeypatch.setattr(backfill_pit_timing, "coverage", lambda *args: [{"eligible_stops": 2}])

    def query(sql: str, settings: object) -> pd.DataFrame:
        if "stg_results" in sql:
            return pd.DataFrame({"season": [2024, 2026], "round": [1, 6]})
        return pd.DataFrame({"exclusion_reason": ["missing_race_replay"], "stops": [1]})

    calls: list[tuple[int, int]] = []

    def build(season: int, rnd: int, **kwargs: object) -> object:
        calls.append((season, rnd))
        return _empty_result()

    monkeypatch.setattr(backfill_pit_timing, "read_query", query)
    monkeypatch.setattr(backfill_pit_timing, "build_pit_timing_sensitivity_incremental", build)
    backfill_pit_timing.main()
    result = json.loads(report.read_text(encoding="utf-8"))
    assert calls == [(2026, 6)]
    assert result["before"] == baseline
    assert result["after"] == [{"eligible_stops": 2}]
    assert len(result["completed"]) == 2
    assert result["exclusions"][0]["exclusion_reason"] == "missing_race_replay"
