from pathlib import Path

PAGES_DIR = Path(__file__).parents[1] / "dashboard" / "pages"
RACE_PAGES = {
    "pit-strategy.md",
    "race-pace.md",
    "race-replay.md",
    "telemetry.md",
    "tyre-strategy.md",
    "weather-and-speed.md",
}


def test_every_race_dropdown_is_scoped_by_season_and_round() -> None:
    pages_with_race_dropdowns = {
        page.name
        for page in PAGES_DIR.glob("*.md")
        if "name=race" in page.read_text()
    }

    assert pages_with_race_dropdowns == RACE_PAGES

    for page_name in pages_with_race_dropdowns:
        content = (PAGES_DIR / page_name).read_text()

        assert "name=season value=season" in content
        assert "name=race value=round label=race_name" in content
        assert "where season = ${inputs.season.value}" in content
        assert "order by round" in content
        assert 'defaultValue="2024 Bahrain Grand Prix"' not in content
        assert "race_label = '${inputs.race.value}'" not in content
        assert "race_name = '${inputs.race.value}'" not in content
