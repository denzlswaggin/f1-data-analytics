"""Command-line interface for the ingestion layer.

Examples::

    python -m ingestion.cli backfill --season 2023
    python -m ingestion.cli backfill --from 2018 --to 2024
    python -m ingestion.cli incremental          # current season only
"""

from __future__ import annotations

from typing import Annotated

import typer

from ingestion.config import get_settings
from ingestion.logging import configure_logging, get_logger
from ingestion.pipeline import backfill as run_backfill
from ingestion.pipeline import ingest_laps
from ingestion.resources import DEFAULT_RESOURCES

app = typer.Typer(add_completion=False, help="F1 data ingestion (Jolpica-F1).")
log = get_logger(__name__)

# Current F1 season — bump each year (or derive from schedule in a later milestone).
CURRENT_SEASON = 2026


def _print_summary(summary: dict[tuple[str, int], int]) -> None:
    total = sum(summary.values())
    for (resource, season), rows in sorted(summary.items()):
        typer.echo(f"  {season}  {resource:<12} {rows:>6} rows")
    typer.echo(f"Total: {total} rows across {len(summary)} resource/season partitions.")


@app.command()
def backfill(
    season: Annotated[int | None, typer.Option(help="Single season to load (e.g. 2023).")] = None,
    from_: Annotated[int | None, typer.Option("--from", help="Start season (inclusive).")] = None,
    to: Annotated[int | None, typer.Option(help="End season (inclusive).")] = None,
    resources: Annotated[
        list[str] | None,
        typer.Option("--resource", help="Resource(s) to load; repeatable."),
    ] = None,
) -> None:
    """Backfill one season (--season) or a range (--from/--to)."""
    configure_logging()
    if season is not None:
        seasons = [season]
    elif from_ is not None and to is not None:
        seasons = list(range(from_, to + 1))
    else:
        raise typer.BadParameter("Provide --season, or both --from and --to.")

    res = tuple(resources) if resources else DEFAULT_RESOURCES
    log.info("cli.backfill.start", seasons=seasons, resources=res, target=get_settings().warehouse)
    summary = run_backfill(seasons, res)
    _print_summary(summary)


@app.command()
def incremental(
    resources: Annotated[
        list[str] | None,
        typer.Option("--resource", help="Resource(s) to load; repeatable."),
    ] = None,
) -> None:
    """Refresh the current season only (idempotent — safe to run repeatedly)."""
    configure_logging()
    res = tuple(resources) if resources else DEFAULT_RESOURCES
    log.info("cli.incremental.start", season=CURRENT_SEASON, resources=res)
    summary = run_backfill([CURRENT_SEASON], res)
    _print_summary(summary)


@app.command()
def laps(
    season: Annotated[int, typer.Option(help="Season to load FastF1 laps for.")],
    from_round: Annotated[int, typer.Option("--from-round", help="First round.")] = 1,
    to_round: Annotated[int, typer.Option("--to-round", help="Last round (inclusive).")] = 5,
    session: Annotated[str, typer.Option(help="FastF1 session: R, Q, S, ...")] = "R",
) -> None:
    """Ingest FastF1 per-lap timing/tyre data (requires the `telemetry` extra)."""
    configure_logging()
    rounds = list(range(from_round, to_round + 1))
    log.info("cli.laps.start", season=season, rounds=rounds, session=session)
    rows = ingest_laps(season, rounds, session)
    typer.echo(f"Loaded {rows} laps for {season} rounds {from_round}-{to_round} ({session}).")


if __name__ == "__main__":
    app()
