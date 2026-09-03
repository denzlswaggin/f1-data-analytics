from pathlib import Path

PAGE = Path(__file__).parents[1] / "dashboard" / "pages" / "pit-strategy.md"


def test_pit_strategy_confidence_reports_full_dataset_coverage() -> None:
    content = PAGE.read_text(encoding="utf-8")
    coverage_query = content.split("```sql pit_coverage", 1)[1].split("```", 1)[0]

    assert "count(*) as sample_rows" in coverage_query
    assert "count(distinct cast(season as varchar)" in coverage_query
    assert "as race_count" in coverage_query
    assert "where season = ${inputs.season.value}" not in coverage_query
    assert 'sampleLabel="pit stops across the published races"' in content
