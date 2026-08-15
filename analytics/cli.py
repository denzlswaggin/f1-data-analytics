"""CLI for analytical transforms.

Example::

    python -m analytics.cli ratings          # build marts.driver_ratings
    python -m analytics.cli ratings --top 20 # ...and print the leaderboard
"""

from __future__ import annotations

from typing import Annotated

import typer
from ingestion.config import get_settings
from ingestion.logging import configure_logging, get_logger

from analytics.pipeline import build_driver_ratings

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


if __name__ == "__main__":
    app()
