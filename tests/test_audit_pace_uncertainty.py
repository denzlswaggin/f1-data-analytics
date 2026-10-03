"""Presentation must distinguish a point difference from supported direction."""

import re
from pathlib import Path

import duckdb
import pytest


@pytest.mark.parametrize(
    ("low", "high", "valid", "eligible", "expected"),
    [
        (0.002, 0.403, 1000, True, "Positive difference"),
        (-0.083, 0.56, 1000, True, "Inconclusive"),
        (-0.9, -0.05, 1000, True, "Negative difference"),
        (0, 0.4, 1000, True, "Inconclusive"),
        (None, None, 0, False, "Interval unavailable"),
        (0.01, 0.4, 899, True, "Interval unavailable"),
        (0.4, 0.01, 1000, True, "Interval unavailable"),
    ],
)
def test_actual_serving_classification(
    low: float | None, high: float | None, valid: int, eligible: bool, expected: str
) -> None:
    with duckdb.connect() as c:
        c.execute("create schema marts")
        c.execute("""create table marts.driver_pace_profile as select
            1 as delta_rank,'a' as driver_id,'Driver A' as driver_name,'country' as nationality,
            0.0 quali_rating,0.17 race_rating,0.17 delta,
            null::double delta_lo,null::double delta_hi,1000 bootstrap_samples,
            1000 bootstrap_valid_samples,true interval_eligible,1 quali_rank,1 race_rank,
            20 n_quali_comparisons,20 n_race_comparisons,3 n_seasons,
            2024 first_season,2026 last_season""")
        c.execute(
            "update marts.driver_pace_profile set delta_lo=?,delta_hi=?,bootstrap_valid_samples=?,interval_eligible=?",
            [low, high, valid, eligible],
        )
        c.execute(
            "create table pace as "
            + Path("dashboard/sources/f1/driver_pace_profile.sql").read_text(encoding="utf-8")
        )
        assert c.execute("select profile from pace").fetchone() == (expected,)
        page = Path("dashboard/pages/saturday-vs-sunday.md").read_text(encoding="utf-8")
        match = re.search(r"```sql difference_intervals\n(.*?)\n```", page, re.S)
        assert match
        result = c.execute(match[1].replace("${pace}", "pace")).fetchone()
        assert result is not None
        assert result[2:4] == ((None, None) if expected == "Interval unavailable" else (low, high))
        c.execute("create schema f1; create table f1.driver_pace_profile as select * from pace")
        coverage = re.search(r"```sql profile_coverage\n(.*?)\n```", page, re.S)
        assert coverage
        row = c.execute(coverage[1]).fetchone()
        assert row is not None
        assert (row[0], row[2]) == (20, 1)
        assert row[5:9] == (None, 2024, 2026, None)


def test_primary_display_uses_paired_intervals_without_specialist_labels() -> None:
    page = Path("dashboard/pages/saturday-vs-sunday.md").read_text(encoding="utf-8")
    assert "<RatingIntervals data={difference_intervals}" in page
    assert "<BarChart" not in page
    assert "not adjusted for screening multiple" in page
    assert "field average" not in page
    assert "seriesColors" not in page
