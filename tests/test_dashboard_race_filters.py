from pathlib import Path

PAGES_DIR = Path(__file__).parents[1] / "dashboard" / "pages"
ROOT = PAGES_DIR.parents[1]
RACE_PAGES = {
    "pit-strategy.md",
    "race-pace.md",
    "telemetry.md",
    "tyre-strategy.md",
    "weather-and-speed.md",
}


def test_every_race_dropdown_is_scoped_by_season_and_round() -> None:
    pages_with_race_dropdowns = {
        page.name
        for page in PAGES_DIR.glob("*.md")
        if "name=race" in page.read_text(encoding="utf-8")
    }

    assert pages_with_race_dropdowns == RACE_PAGES

    for page_name in pages_with_race_dropdowns:
        content = (PAGES_DIR / page_name).read_text(encoding="utf-8")

        assert "name=season value=season" in content
        assert 'name=race value=round label=race_label order="round asc"' in content
        assert "where season = ${inputs.season.value}" in content
        assert "order by round" in content
        assert "lpad(cast(round as varchar), 2, '0')" in content
        assert 'defaultValue="2024 Bahrain Grand Prix"' not in content
        assert "race_label = '${inputs.race.value}'" not in content
        assert "race_name = '${inputs.race.value}'" not in content


def test_race_replay_redirects_to_the_dedicated_app() -> None:
    page = (PAGES_DIR / "race-replay.md").read_text(encoding="utf-8")
    component = (PAGES_DIR.parent / "components" / "ReplayRedirect.svelte").read_text(
        encoding="utf-8"
    )

    assert "<ReplayRedirect />" in page
    assert "window.location.replace(target)" in component
    assert "current.port = '5173'" in component
    assert "'/f1-data-analytics/replay/'" in component
    assert "<a href={target}>Open race replay</a>" in component


def test_replay_is_published_beside_the_evidence_dashboard() -> None:
    vite_config = (ROOT / "web" / "vite.config.ts").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "deploy-dashboard.yml").read_text(encoding="utf-8")

    assert "'/f1-data-analytics/replay'" in vite_config
    assert "npm --prefix web run build:with-data" in workflow
    assert "cp -R web/build/. dashboard/build/replay/" in workflow
    assert "dashboard/package-lock.json" in workflow
    assert "web/package-lock.json" in workflow
