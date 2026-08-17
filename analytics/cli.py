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

from analytics.pipeline import build_driver_ratings, build_race_replay, build_race_replays

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
    season: Annotated[int, typer.Option(help="Season to build race replays for.")],
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
) -> None:
    """Build the animated race-replay mart (marts.race_replay).

    With ``--round`` builds one race (replacing the mart); without it, builds every
    completed round of the season so the dashboard can offer a race picker.
    """
    configure_logging()
    log.info(
        "cli.replay.start", season=season, round=round_, tick=tick, target=get_settings().warehouse
    )
    if round_ is not None:
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


if __name__ == "__main__":
    app()
