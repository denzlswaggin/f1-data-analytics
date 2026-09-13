from pathlib import Path

ROOT = Path(__file__).parents[1]
PAGE = ROOT / "dashboard" / "pages" / "racecraft-battles.md"
BATTLES_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "racecraft_battles.sql"
SUMMARY_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "racecraft_driver_summary.sql"
COVERAGE_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "data_coverage.sql"
NAV = ROOT / "dashboard" / "components" / "AppNav.svelte"


def test_page_keeps_attack_defence_and_uncertainty_separate() -> None:
    page = PAGE.read_text(encoding="utf-8")

    assert "attack_conversion_p05_pct" in page
    assert "defence_hold_p95_pct" in page
    assert "offense_eligible and defense_eligible" in page
    assert "does not combine" in page
    assert "Interrupted" in page
    assert "not a driver-skill score" in page
    assert "not official DRS" in page


def test_sources_publish_battles_summaries_and_empty_sentinels() -> None:
    battles = BATTLES_SOURCE.read_text(encoding="utf-8")
    summary = SUMMARY_SOURCE.read_text(encoding="utf-8")
    coverage = COVERAGE_SOURCE.read_text(encoding="utf-8")

    assert "from marts.racecraft_battles" in battles
    assert "where not exists" in battles
    assert "from marts.racecraft_driver_summary" in summary
    assert "where not exists" in summary
    assert "'racecraft'" in coverage


def test_driver_navigation_links_to_racecraft_page() -> None:
    navigation = NAV.read_text(encoding="utf-8")
    assert "{ label: 'Racecraft battles', path: 'racecraft-battles' }" in navigation


def test_page_distinguishes_continuous_evidence_and_reversal_ownership() -> None:
    page = PAGE.read_text(encoding="utf-8")
    for field in ("pressure_seconds", "longest_pressure_run_s", "release_run_s"):
        assert f"<Column id={field}" in page
    assert "Total pressure may" in page
    assert "eligibility uses the longest" in page
    assert "measured elapsed seconds" in page
    assert "missed expected replay sample" in page
    assert "defender receives the re-pass made" in page
    assert "attacker receives the re-pass" in page
    assert "quick_reversals_conceded" in page


def test_page_shows_resolved_denominator_and_excluded_role_counts() -> None:
    page = PAGE.read_text(encoding="utf-8")
    for field in (
        "interrupted_attacks",
        "unresolved_attacks",
        "interrupted_defences",
        "unresolved_defences",
        "offense_confidence",
        "defense_confidence",
    ):
        assert f"<Column id={field}" in page
    assert 'title="Resolved denominator"' in page
    assert "not the probability of passing" in page
    assert "event-detection errors" in page
    assert "not counted as failed" in page


def test_headline_counts_partition_all_observed_battles() -> None:
    import duckdb

    page = PAGE.read_text(encoding="utf-8")
    query = page.split("```sql race_totals\n", 1)[1].split("```", 1)[0]
    query = query.replace("${race_battles}", "battles")
    with duckdb.connect() as connection:
        connection.execute("create table battles (eligible boolean, outcome varchar)")
        for outcome, eligible in (
            ("Converted", True),
            ("Defended", True),
            ("Converted", False),
            ("Defended", False),
            ("Interrupted", False),
            ("Unresolved", False),
        ):
            connection.execute("insert into battles values (?, ?)", [eligible, outcome])
        row = connection.execute(query).fetchdf().iloc[0]
    assert row["observed_battles"] == 6
    assert row["eligible_battles"] == row["conversions"] + row["defences"] == 2
    assert row["excluded_resolved"] == 2
    assert row["interrupted_battles"] == row["unresolved_battles"] == 1


def test_pair_scope_combines_directions_and_filters_episode_drilldown() -> None:
    import duckdb

    page = PAGE.read_text(encoding="utf-8")
    pair_query = page.split("```sql battle_pairs\n", 1)[1].split("```", 1)[0]
    pair_query = pair_query.replace("${race_battles}", "battles")
    pair_query = pair_query.replace("${inputs.race.value}", "1")
    detail = page.split("```sql pair_battles\n", 1)[1].split("```", 1)[0]
    detail = detail.replace("${race_battles}", "battles").replace("${inputs.pair.value}", "A / B")
    with duckdb.connect() as connection:
        connection.execute("""create table battles as select * from (values
            (2026, 1, 'A', 'B', true, true, false, 'Converted', 10.0, 100.0),
            (2026, 2, 'B', 'A', true, false, true, 'Defended', 20.0, 200.0),
            (2026, 2, 'A', 'C', false, false, false, 'Interrupted', 5.0, 300.0),
            (2026, 2, 'A', 'B', false, false, false, 'Unresolved', 15.0, 400.0)
            ) t(season, round, attacker_code, defender_code, eligible, converted,
                defender_retained, outcome, pressure_seconds, start_t_s)""")
        season = connection.execute(pair_query.replace("${inputs.view.value}", "season")).fetchdf()
        pair = season.loc[season["pair"].eq("A / B")].iloc[0]
        assert pair["round"] == 0
        assert pair["episodes"] == 3
        assert pair["races"] == 2
        assert pair["confirmed_passes"] == pair["clean_defences"] == 1
        assert pair["unresolved"] == 1
        assert pair["pressure_seconds"] == 45
        episodes = connection.execute(detail).fetchdf()
        assert episodes["attacker_code"].tolist() == ["A", "B", "A"]
        assert episodes["round"].tolist() == [1, 2, 2]
        # Race-scoped input is already filtered by the page's race_battles query.
        connection.execute("delete from battles where round != 1")
        race = connection.execute(pair_query.replace("${inputs.view.value}", "race")).fetchdf()
        assert len(race) == 1
        assert race.iloc[0]["round"] == 1
        assert race.iloc[0]["episodes"] == race.iloc[0]["races"] == 1
