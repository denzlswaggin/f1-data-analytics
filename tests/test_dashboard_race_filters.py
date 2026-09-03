from pathlib import Path

PAGES_DIR = Path(__file__).parents[1] / "dashboard" / "pages"
RACE_PAGES = {
    "pit-strategy.md",
    "race-pace.md",
    "telemetry.md",
    "tyre-strategy.md",
    "weather-and-speed.md",
}


def test_every_race_dropdown_is_scoped_by_season_and_round() -> None:
    pages_with_race_dropdowns = {
        page.name for page in PAGES_DIR.glob("*.md") if "name=race" in page.read_text()
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


def test_replay_picker_resets_the_race_when_the_season_changes() -> None:
    page = (PAGES_DIR / "race-replay.md").read_text(encoding="utf-8")
    component = (PAGES_DIR.parent / "components" / "ReplayRacePicker.svelte").read_text(
        encoding="utf-8"
    )

    assert "<ReplayRacePicker seasons={replay_seasons} races={replay_races} />" in page
    assert "cast(season as integer) as season" in page
    assert "cast(round as integer) as round" in page
    assert "cast(cast(season as integer) as varchar)" in page
    assert "substr(race_name, strpos(race_name, ' ') + 1)" in page
    assert (
        "where season = ${inputs.season.value}"
        not in page.split("```sql replay_races", 1)[1].split("```", 1)[0]
    )
    assert "const seasonChanged" in component
    assert "const requestedRace = seasonChanged ? null : rawValue('race')" in component
    assert "publish('race', firstRace.round, firstRace.race_name)" in component
    assert "a truncated upstream feed is withheld" in page
