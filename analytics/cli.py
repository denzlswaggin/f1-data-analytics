"""CLI for analytical transforms.

Example::

    python -m analytics.cli ratings          # build marts.driver_ratings
    python -m analytics.cli ratings --top 20 # ...and print the leaderboard
    python -m analytics.cli replay --season 2026 --round 1  # build marts.race_replay
"""

from __future__ import annotations

from typing import Annotated

import typer
from ingestion.config import get_settings
from ingestion.logging import configure_logging, get_logger
from ingestion.pipeline import season_rounds

from analytics.pipeline import (
    build_all_overtakes,
    build_all_replays,
    build_driver_ratings,
    build_race_overtakes,
    build_race_overtakes_season,
    build_race_replay,
    build_race_replays,
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
) -> None:
    """Build the global teammate-normalised driver rating mart."""
    configure_logging()
    log.info("cli.ratings.start", target=get_settings().warehouse)
    df = build_driver_ratings()

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
    typer.echo(
        f"Built marts.race_replay for {season} {scope}: "
        f"{len(df)} rows, {df['driver_code'].nunique()} drivers, "
        f"{df['round'].nunique()} race(s) at {tick}s ticks."
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
