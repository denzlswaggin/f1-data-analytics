from pathlib import Path

PAGE = Path(__file__).parents[1] / "dashboard" / "pages" / "pit-strategy.md"


def test_pit_strategy_reports_selected_race_coverage() -> None:
    content = PAGE.read_text(encoding="utf-8")
    coverage_query = content.split("```sql pit_coverage", 1)[1].split("```", 1)[0]
    assert "from f1.data_coverage" in coverage_query
    assert "section = 'pit_cycle'" in coverage_query
    assert "season = ${inputs.season.value}" in coverage_query
    assert "round = ${inputs.race.value}" in coverage_query
    assert 'sampleLabel="recorded pit visits"' in content
