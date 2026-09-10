"""CLI for analytical transforms.

Example::

    python -m analytics.cli ratings          # build marts.driver_ratings
    python -m analytics.cli ratings --top 20 # ...and print the leaderboard
    python -m analytics.cli validate         # backtest + CIs + shrinkage sweep
    python -m analytics.cli validate --race  # ...the same checks on the race-pace rating
    python -m analytics.cli replay --season 2026 --round 1  # build marts.race_replay
    python -m analytics.cli pace-profile --from-season 2022  # Saturday vs Sunday
"""

from __future__ import annotations

from typing import Annotated

import pandas as pd
import typer
from ingestion.config import get_settings
from ingestion.loaders.warehouse import read_query
from ingestion.logging import configure_logging, get_logger
from ingestion.pipeline import season_rounds

from analytics.pipeline import (
    build_all_overtakes,
    build_all_replays,
    build_all_traffic_adjusted_pace,
    build_driver_pace_profile,
    build_driver_ratings,
    build_driver_ratings_v2,
    build_driver_ratings_v3,
    build_race_overtakes,
    build_race_overtakes_season,
    build_race_replay,
    build_race_replays,
    build_traffic_adjusted_pace,
)
from analytics.validation import (
    backtest_ratings,
    bootstrap_ratings,
    compare_dynamic_backtest,
    shrinkage_sensitivity,
)

_GAPS_QUERY = (
    "select driver_id, teammate_id, pace_gap, season from intermediate.int_teammate_quali_gaps"
)

# The race gaps carry the same four columns at the same grain, so every check in
# analytics.validation applies to them unchanged.
_RACE_GAPS_QUERY = (
    "select driver_id, teammate_id, pace_gap, season from intermediate.int_teammate_race_gaps"
)

app = typer.Typer(add_completion=False, help="F1 analytical transforms.")
log = get_logger(__name__)


@app.callback()
def _main() -> None:
    """F1 analytical transforms (keeps subcommands named)."""


@app.command()
def ratings(
    top: Annotated[int, typer.Option(help="Print the top-N leaderboard after building.")] = 20,
    min_comparisons: Annotated[
        int, typer.Option(help="Min teammate comparisons to show in the printed list.")
    ] = 20,
    n_boot: Annotated[
        int, typer.Option(help="Comparison-bootstrap resamples for rating intervals.")
    ] = 300,
) -> None:
    """Build the global teammate-normalised driver rating mart."""
    configure_logging()
    log.info("cli.ratings.start", target=get_settings().warehouse)
    df = build_driver_ratings(n_boot=n_boot)

    shown = df[df["n_comparisons"] >= min_comparisons].head(top)
    typer.echo(
        f"\nTop {len(shown)} drivers by teammate-normalised pace "
        f"(min {min_comparisons} comparisons):\n"
    )
    typer.echo(f"  {'#':>3}  {'driver':<22} {'rating':>7}  {'races':>5}  seasons")
    for row in shown.itertuples():
        name = row.driver_name or row.driver_id
        typer.echo(
            f"  {row.rank:>3}  {name:<22} {row.rating:>7.3f}  "
            f"{row.n_comparisons:>5}  {row.first_season}-{row.last_season}"
        )


@app.command("ratings-v2")
def ratings_v2(
    top: Annotated[int, typer.Option(help="Print the top-N latest-season ratings.")] = 20,
    n_boot: Annotated[
        int, typer.Option(help="Race-cluster bootstrap resamples for intervals.")
    ] = 100,
    temporal_weight: Annotated[
        float, typer.Option(help="Smoothness strength between a driver's seasons.")
    ] = 48.0,
) -> None:
    """Build dynamic driver-season ratings with race-cluster uncertainty."""
    configure_logging()
    df = build_driver_ratings_v2(n_boot=n_boot, temporal_weight=temporal_weight)
    latest_season = int(df["season"].max())
    shown = df[df["season"] == latest_season].head(top)
    typer.echo(f"\nDynamic ratings for {latest_season} (top {len(shown)}):\n")
    typer.echo(f"  {'#':>3}  {'driver':<22} {'rating':>7}  {'change':>7}  {'90% CI':>18}")
    for row in shown.itertuples():
        name = row.driver_name or row.driver_id
        change = "n/a" if pd.isna(row.form_delta) else f"{row.form_delta:+.3f}"
        typer.echo(
            f"  {row.rank:>3}  {name:<22} {row.rating:>7.3f}  {change:>7}  "
            f"[{row.rating_lo:>6.3f}, {row.rating_hi:>6.3f}]"
        )


@app.command("ratings-v3")
def ratings_v3(
    final_holdout_season: Annotated[
        int, typer.Option(help="Untouched final test season; 2026 when available.")
    ] = 2026,
    n_boot: Annotated[
        int, typer.Option(help="Race-weekend bootstrap resamples for rating intervals.")
    ] = 100,
    seed: Annotated[int, typer.Option(help="Deterministic bootstrap seed.")] = 0,
    top: Annotated[int, typer.Option(help="Print the top-N latest-season research ratings.")] = 20,
) -> None:
    """Build the opt-in joint V3 experiment and evaluation artifacts."""
    configure_logging()
    result = build_driver_ratings_v3(
        final_holdout_season=final_holdout_season,
        n_boot=n_boot,
        seed=seed,
    )
    typer.echo(f"\nSelected V3 parameters: {result.selected_parameters.label}")
    typer.echo(f"Final holdout {final_holdout_season}: {result.holdout_status}")
    typer.echo(
        "Promotion gate: "
        + ("passed" if result.recommended_for_promotion else "not passed; V1/V2 remain canonical")
    )
    latest = int(result.ratings["season"].max())
    shown = result.ratings[result.ratings["season"] == latest].head(top)
    typer.echo(f"\nExperimental joint ratings for {latest} (top {len(shown)}):\n")
    typer.echo(
        f"  {'#':>3}  {'driver':<22} {'joint':>7}  {'quali':>7}  {'race':>7}  {'90% CI':>18}"
    )
    for row in shown.itertuples():
        name = row.driver_name or row.driver_id
        typer.echo(
            f"  {row.rank:>3}  {name:<22} {row.rating:>7.3f}  "
            f"{row.quali_rating:>7.3f}  {row.race_rating:>7.3f}  "
            f"[{row.rating_lo:>6.3f}, {row.rating_hi:>6.3f}]"
        )


@app.command()
def validate(
    n_boot: Annotated[
        int, typer.Option(help="Bootstrap resamples for the rating CIs (0 to skip).")
    ] = 300,
    prior_weight: Annotated[
        float, typer.Option(help="Empirical-Bayes shrinkage strength for the fit.")
    ] = 8.0,
    top: Annotated[int, typer.Option(help="Rows of the bootstrap CI table to print.")] = 15,
    race: Annotated[
        bool,
        typer.Option("--race", help="Validate the race-pace rating instead of qualifying."),
    ] = False,
) -> None:
    """Validate the rating model: temporal backtest, shrinkage sensitivity, bootstrap CIs."""
    configure_logging()
    which = "race" if race else "qualifying"
    log.info("cli.validate.start", gaps=which, target=get_settings().warehouse)
    gaps = read_query(_RACE_GAPS_QUERY if race else _GAPS_QUERY)
    if gaps.empty:
        typer.echo(f"No {which} teammate gaps found — build the dbt intermediate models first.")
        return

    typer.echo(f"\nValidating the {which} rating.")

    bt = backtest_ratings(gaps, prior_weight=prior_weight)
    typer.echo("\n=== Backtest (expanding-window temporal hold-out) ===")
    typer.echo(
        f"  predictions       : {bt.n_predictions} races over {bt.n_test_seasons} test seasons"
    )
    typer.echo(f"  race sign acc.    : {bt.sign_accuracy:.3f}   (0.50 = coin flip)")
    typer.echo(
        f"  season-battle acc : {bt.pair_sign_accuracy:.3f}   over {bt.n_pairs} teammate-season battles"
    )
    typer.echo(f"  correlation r     : {bt.pearson_r:.3f}")
    typer.echo(
        f"  MAE / baseline    : {bt.mae:.2f} / {bt.baseline_mae:.2f}  (skill {bt.skill_score:+.3f})"
    )

    comparison = compare_dynamic_backtest(gaps)
    typer.echo("\n=== Static vs dynamic temporal hold-out ===")
    typer.echo(f"  predictions       : {comparison.n_predictions}")
    typer.echo(f"  MAE static/dynamic: {comparison.static_mae:.3f} / {comparison.dynamic_mae:.3f}")
    typer.echo(
        "  sign static/dyn.  : "
        f"{comparison.static_sign_accuracy:.3f} / {comparison.dynamic_sign_accuracy:.3f}"
    )

    sens = shrinkage_sensitivity(gaps)
    typer.echo("\n=== Shrinkage sensitivity (leaderboard stability vs prior_weight) ===")
    typer.echo(f"  {'prior_wt':>8}  {'spearman':>8}  {'top20':>6}  {'|rating|':>8}")
    for r in sens.itertuples():
        typer.echo(
            f"  {r.prior_weight:>8.1f}  {r.spearman_vs_default:>8.3f}  "
            f"{r.top_n_overlap:>6.2f}  {r.mean_abs_rating:>8.3f}"
        )

    if n_boot > 0:
        ci = bootstrap_ratings(gaps, n_boot=n_boot, prior_weight=prior_weight)
        typer.echo(f"\n=== Bootstrap 90% CIs (n_boot={n_boot}) — top {top} ===")
        typer.echo(f"  {'#':>3}  {'driver':<18} {'rating':>7}  {'90% CI':>18}  boots")
        for i, r in enumerate(ci.head(top).itertuples(), start=1):
            typer.echo(
                f"  {i:>3}  {r.driver_id:<18} {r.rating:>7.3f}  "
                f"[{r.rating_lo:>6.3f}, {r.rating_hi:>6.3f}]  {r.n_boot}"
            )


@app.command("pace-profile")
def pace_profile(
    from_season: Annotated[
        int | None, typer.Option("--from-season", help="First season of race pace to include.")
    ] = None,
    to_season: Annotated[
        int | None, typer.Option("--to-season", help="Last season of race pace to include.")
    ] = None,
    top: Annotated[int, typer.Option(help="Print the top-N racers and specialists.")] = 10,
    min_races: Annotated[
        int, typer.Option(help="Min race comparisons to show in the printed lists.")
    ] = 10,
) -> None:
    """Build the Saturday-vs-Sunday pace profile (quali rating vs race rating)."""
    configure_logging()
    log.info(
        "cli.pace-profile.start",
        from_season=from_season,
        to_season=to_season,
        target=get_settings().warehouse,
    )
    df = build_driver_pace_profile(from_season, to_season)
    if df.empty:
        typer.echo(
            "No pace profile built — ingest FastF1 laps and build the dbt intermediate "
            "models first (needs int_teammate_race_gaps)."
        )
        return

    shown = df[df["n_race_comparisons"] >= min_races]
    typer.echo(
        f"\nSaturday vs Sunday — delta = race rating - quali rating "
        f"(min {min_races} race comparisons):\n"
    )

    def _table(title: str, rows: pd.DataFrame) -> None:
        typer.echo(f"  {title}")
        typer.echo(
            f"  {'#':>3}  {'driver':<22} {'delta':>7}  {'quali':>7}  {'race':>7}  {'races':>5}"
        )
        for row in rows.itertuples():
            name = row.driver_name or row.driver_id
            typer.echo(
                f"  {row.delta_rank:>3}  {name:<22} {row.delta:>+7.3f}  "
                f"{row.quali_rating:>7.3f}  {row.race_rating:>7.3f}  "
                f"{row.n_race_comparisons:>5}"
            )
        typer.echo("")

    _table(f"Top {top} racers (gain most on Sunday)", shown.head(top))
    # Only worth a second table when it would not just repeat the first one.
    if len(shown) > top:
        _table(
            f"Top {top} qualifying specialists (lose most on Sunday)",
            shown.tail(top).iloc[::-1],
        )


@app.command()
def replay(
    season: Annotated[
        int | None, typer.Option(help="Season to build race replays for (not needed with --all).")
    ] = None,
    round_: Annotated[
        int | None,
        typer.Option("--round", help="Single round; omit to build all completed rounds."),
    ] = None,
    tick: Annotated[
        float,
        typer.Option(help="Time-grid resolution in seconds (smaller = smoother, bigger file)."),
    ] = 1.0,
    retire_buffer: Annotated[
        float | None,
        typer.Option(
            "--retire-buffer",
            help="Seconds a retired car stays shown after it stops (default: F1_REPLAY_RETIRE_BUFFER_S).",
        ),
    ] = None,
    all_seasons: Annotated[
        bool,
        typer.Option(
            "--all", help="Build every race with positions (all seasons); ignores --season."
        ),
    ] = False,
) -> None:
    """Build the animated race-replay mart (marts.race_replay).

    With ``--round`` builds one race (replacing the mart); with ``--all`` builds every
    race that has positions across all seasons; otherwise builds every completed round
    of ``--season`` so the dashboard can offer a race picker.
    """
    configure_logging()
    log.info(
        "cli.replay.start", season=season, round=round_, tick=tick, target=get_settings().warehouse
    )
    if all_seasons:
        df = build_all_replays(tick_s=tick, retire_buffer_s=retire_buffer)
        scope = "all seasons"
    elif season is None:
        raise typer.BadParameter("Provide --season, or use --all.")
    elif round_ is not None:
        df = build_race_replay(season, round_, tick_s=tick, retire_buffer_s=retire_buffer)
        scope = f"round {round_}"
    else:
        rounds = season_rounds(season, completed_only=True)
        df = build_race_replays(season, rounds, tick_s=tick, retire_buffer_s=retire_buffer)
        scope = f"rounds {rounds[0]}-{rounds[-1]}" if rounds else "(no rounds)"
    if df.empty:
        typer.echo(f"No replay data for {season} {scope} (need positions + laps ingested).")
        return
    race_count = df[["season", "round"]].drop_duplicates().shape[0]
    label = scope if season is None else f"{season} {scope}"
    typer.echo(
        f"Built marts.race_replay for {label}: {len(df)} rows, "
        f"{df['driver_code'].nunique()} drivers, {race_count} race(s) at {tick}s ticks."
    )


@app.command("traffic-pace")
def traffic_pace(
    season: Annotated[int | None, typer.Option(help="Season of the race to analyse.")] = None,
    round_: Annotated[int | None, typer.Option("--round", help="Round to analyse.")] = None,
    all_races: Annotated[
        bool,
        typer.Option("--all", help="Build every race currently present in the replay mart."),
    ] = False,
) -> None:
    """Build clean-air pace and traffic-associated delta marts."""
    configure_logging()
    if all_races:
        result = build_all_traffic_adjusted_pace()
        scope = "all replay races"
    elif season is not None and round_ is not None:
        result = build_traffic_adjusted_pace(season, round_)
        scope = f"{season} round {round_}"
    else:
        raise typer.BadParameter("Provide --season and --round together, or use --all.")
    publishable = int(result.summary["traffic_adjusted_pace_delta_sec"].notna().sum())
    typer.echo(
        f"Built traffic pace for {scope}: {len(result.summary)} driver-races, "
        f"{publishable} with publishable clean-air pace."
    )


@app.command()
def overtakes(
    season: Annotated[
        int | None, typer.Option(help="Season to detect overtakes for (not needed with --all).")
    ] = None,
    round_: Annotated[
        int | None,
        typer.Option("--round", help="Single round; omit to do every round in the replay mart."),
    ] = None,
    battle_gap: Annotated[
        float | None,
        typer.Option("--battle-gap", help="Max post-pass interval, s (F1_OVERTAKE_BATTLE_GAP_S)."),
    ] = None,
    persist: Annotated[
        float | None,
        typer.Option(
            "--persist", help="Seconds the passer must stay ahead (F1_OVERTAKE_PERSIST_S)."
        ),
    ] = None,
    start_guard: Annotated[
        float | None,
        typer.Option(
            "--start-guard", help="Skip passes before this many s (F1_OVERTAKE_START_GUARD_S)."
        ),
    ] = None,
    proximity_frac: Annotated[
        float | None,
        typer.Option(
            "--proximity-frac",
            help="Physical-proximity gate as a fraction of track extent (F1_OVERTAKE_PROXIMITY_FRAC).",
        ),
    ] = None,
    all_seasons: Annotated[
        bool,
        typer.Option("--all", help="Detect for every race in the replay mart; ignores --season."),
    ] = False,
) -> None:
    """Detect on-track overtakes into marts.race_overtakes (from marts.race_replay).

    Reads the already-built replay mart, so build the replay first. With ``--round``
    does one race (replacing the mart); with ``--all`` every race across seasons;
    otherwise every round of ``--season`` present in the replay mart.
    """
    configure_logging()
    settings = get_settings()
    overrides = {
        "overtake_battle_gap_s": battle_gap,
        "overtake_persist_s": persist,
        "overtake_start_guard_s": start_guard,
        "overtake_proximity_frac": proximity_frac,
    }
    overrides = {k: v for k, v in overrides.items() if v is not None}
    if overrides:
        settings = settings.model_copy(update=overrides)
    log.info("cli.overtakes.start", season=season, round=round_, target=settings.warehouse)

    if all_seasons:
        df = build_all_overtakes(settings=settings)
        scope = "all seasons"
    elif season is None:
        raise typer.BadParameter("Provide --season, or use --all.")
    elif round_ is not None:
        df = build_race_overtakes(season, round_, settings=settings)
        scope = f"{season} round {round_}"
    else:
        df = build_race_overtakes_season(season, settings=settings)
        scope = f"{season} (all rounds)"
    if df.empty:
        typer.echo(f"No overtakes for {scope} (build marts.race_replay first).")
        return
    races = df[["season", "round"]].drop_duplicates().shape[0]
    typer.echo(f"Built marts.race_overtakes for {scope}: {len(df)} passes across {races} race(s).")


if __name__ == "__main__":
    app()
