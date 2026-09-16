from pathlib import Path

ROOT = Path(__file__).parents[1]
PAGE = ROOT / "dashboard" / "pages" / "driver-dna.md"
PROFILE = ROOT / "dashboard" / "components" / "DriverDNAProfile.svelte"
HEATMAP = ROOT / "dashboard" / "components" / "DriverDNAHeatmap.svelte"
LAP = ROOT / "dashboard" / "components" / "DriverDNALap.svelte"
INSIGHTS = ROOT / "dashboard" / "components" / "DriverDNAInsights.svelte"
EVOLUTION = ROOT / "dashboard" / "components" / "DriverDNAEvolution.svelte"
RACE_INSIGHTS = ROOT / "dashboard" / "components" / "DriverDNARaceInsights.svelte"
STABILITY_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "driver_dna_stability.sql"


def test_driver_dna_page_exposes_driver_season_and_race_filters() -> None:
    page = PAGE.read_text(encoding="utf-8")

    assert "name=from_season" in page
    assert "name=to_season" in page
    assert "defaultValue={2025}" in page
    assert "defaultValue={2026}" in page
    assert "name=driver_a" in page
    assert "name=driver_b" in page
    assert "name=dna_race" in page
    assert "|| ' vs ' || teammate_name as race_label" in page


def test_driver_dna_has_five_diverging_axes_and_no_radar_or_composite() -> None:
    page = PAGE.read_text(encoding="utf-8")
    profile = PROFILE.read_text(encoding="utf-8")

    for label in (
        "Full throttle distance",
        "Coasting distance",
        "Braking distance",
        "Brake-onset speed",
        "Low-speed corner speed",
    ):
        assert label in page
    assert "zero-line" in profile
    assert "interval" in profile
    assert "radar" not in (page + profile).lower()
    assert "No composite score or rank" in page


def test_driver_dna_adds_independent_single_season_peer_average() -> None:
    page = PAGE.read_text(encoding="utf-8")
    profile = PROFILE.read_text(encoding="utf-8")

    assert "## Driver vs. season average" in page
    assert "name=benchmark_season" in page
    assert "name=benchmark_driver" in page
    assert "<DependentDropdown data={benchmark_drivers}" in page
    assert "where from_season = to_season" in page
    assert "having count(*) >= 2" in page
    assert "driver_code <> '${inputs.benchmark_driver.value}'" in page
    for metric in (
        "full_throttle_share",
        "coasting_share",
        "braking_share",
        "brake_onset_speed_kph",
        "low_speed_kph",
    ):
        assert f"avg({metric})" in page
    assert "Drivers in peer average" in page
    assert "individual profile intervals cannot be combined" in page
    assert "{#if row.lo != null && row.hi != null}" in profile
    assert "?? '—'" not in profile


def test_driver_dna_interprets_stability_evolution_and_defining_races() -> None:
    page = PAGE.read_text(encoding="utf-8")
    insights = INSIGHTS.read_text(encoding="utf-8")
    evolution = EVOLUTION.read_text(encoding="utf-8")
    race_insights = RACE_INSIGHTS.read_text(encoding="utf-8")

    assert "from f1.driver_dna_stability" in page
    assert "and from_season = least(" in page
    assert "Stable signature" in page
    assert "Context-dependent" in page
    assert "Inconclusive" in page
    assert "rows between 4 preceding and current row" in page
    assert "count(value) over technique_window >= 3" in page
    assert "profile_distance_z" in page
    assert "influence_score_z" in page
    assert "(select count(*) from ${driver_race_profiles}) >= 6" in page
    assert 'data-testid="driver-dna-insights"' in insights
    assert 'data-testid="driver-dna-evolution"' in evolution
    assert 'data-testid="driver-dna-race-insights"' in race_insights
    assert "three laps and three tyre-life laps" in page
    assert "ten laps and ten tyre-life laps" not in page
    assert "from marts.driver_dna_stability" in STABILITY_SOURCE.read_text(encoding="utf-8")


def test_driver_dna_lap_has_tooltips_synchronised_traces_and_empty_state() -> None:
    page = PAGE.read_text(encoding="utf-8")
    heatmap = HEATMAP.read_text(encoding="utf-8")
    lap = LAP.read_text(encoding="utf-8")

    assert "on:mouseenter={() => active = index}" in lap
    assert "selected.end_distance_m" in lap
    assert "driver_speed_kph" in lap
    assert "driver_throttle" in lap
    assert "driver_brake_share" in lap
    assert "No eligible same-compound green-flag lap" in lap
    assert "No eligible race evidence" in heatmap
    assert "Largest 200 m gain" in page
    assert "Largest 200 m loss" in page


def test_driver_dna_components_stack_on_mobile() -> None:
    lap = LAP.read_text(encoding="utf-8")
    profile = PROFILE.read_text(encoding="utf-8")

    assert "@media (max-width: 680px)" in lap
    assert ".layout { grid-template-columns: 1fr; }" in lap
    assert "@media (max-width: 560px)" in profile
    assert "@media (max-width: 680px)" in INSIGHTS.read_text(encoding="utf-8")
    assert "@media (max-width: 620px)" in EVOLUTION.read_text(encoding="utf-8")
    assert "@media (max-width: 680px)" in RACE_INSIGHTS.read_text(encoding="utf-8")
    assert "<ExpandableSection" in PAGE.read_text(encoding="utf-8")
