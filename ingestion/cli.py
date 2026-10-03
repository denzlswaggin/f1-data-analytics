"""Command-line interface for the ingestion layer.

Examples::

    python -m ingestion.cli backfill --season 2024
    python -m ingestion.cli backfill --from 2024 --to 2026
    python -m ingestion.cli incremental          # current season only
    python -m ingestion.cli laps --season 2024 --incremental   # only new rounds
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ingestion.config import FIRST_SEASON, LAST_SEASON, get_settings
from ingestion.health import evaluate_pipeline_health, record_pipeline_health
from ingestion.logging import configure_logging, get_logger
from ingestion.maintenance import (
    create_postgres_backup,
    latest_postgres_backup,
    run_postgres_restore_drill,
)
from ingestion.pipeline import backfill as run_backfill
from ingestion.pipeline import (
    ingest_ergast_laps,
    ingest_laps,
    ingest_openf1_timing,
    ingest_pitstops,
    ingest_positions,
    ingest_race_control,
    ingest_team_radio,
    ingest_telemetry,
    ingest_weather,
    season_rounds,
)
from ingestion.recovery import restore_lake_partition
from ingestion.resources import DEFAULT_RESOURCES

app = typer.Typer(add_completion=False, help="F1 data ingestion (Jolpica-F1).")
log = get_logger(__name__)

# Shared options reused across the per-round ingest commands.
FromRoundOpt = Annotated[int, typer.Option("--from-round", help="First round.")]
ToRoundOpt = Annotated[
    int | None, typer.Option("--to-round", help="Last round; default = last completed.")
]
SessionOpt = Annotated[str, typer.Option(help="FastF1 session: R, Q, S, ...")]
IncrementalOpt = Annotated[
    bool,
    typer.Option(
        "--incremental",
        help="Load only rounds past the high-watermark (max round already in raw.<table>).",
    ),
]
FastestOnlyOpt = Annotated[
    bool,
    typer.Option(
        "--fastest-only",
        help="Store only each driver's fastest timed lap for dashboard coverage.",
    ),
]


def _print_summary(summary: dict[tuple[str, int], int]) -> None:
    total = sum(summary.values())
    for (resource, season), rows in sorted(summary.items()):
        typer.echo(f"  {season}  {resource:<12} {rows:>6} rows")
    typer.echo(f"Total: {total} rows across {len(summary)} resource/season partitions.")


def _resolve_rounds(
    season: int,
    from_round: int,
    to_round: int | None,
    *,
    incremental: bool = False,
    table: str | None = None,
) -> list[int]:
    """Build a round range; when ``to_round`` is omitted, use the last completed
    round from the ingested schedule (``raw.races``) — i.e. "season so far".

    With ``incremental`` and a ``table``, start just past the highest round
    already loaded for that table (the high-watermark), so only new rounds are
    fetched. Returns ``[]`` when there is nothing new to load.
    """
    if incremental and table is not None:
        from ingestion.loaders.warehouse import latest_loaded_round

        from_round = max(from_round, latest_loaded_round(table, season) + 1)
    if to_round is None:
        completed = season_rounds(season, completed_only=True)
        to_round = max(completed) if completed else from_round
    return list(range(from_round, to_round + 1))


def _echo_rounds(rows: int, season: int, rounds: list[int], noun: str, suffix: str = "") -> None:
    """Print a per-round ingest summary (rounds is always non-empty here)."""
    typer.echo(f"Loaded {rows} {noun} for {season} rounds {rounds[0]}-{rounds[-1]}{suffix}.")


@app.command()
def backfill(
    season: Annotated[int | None, typer.Option(help="Single season to load (2024-2026).")] = None,
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
    if not seasons or seasons[0] < FIRST_SEASON or seasons[-1] > LAST_SEASON:
        raise typer.BadParameter(f"Seasons must be within {FIRST_SEASON}-{LAST_SEASON}.")

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
    """Refresh the current season's Jolpica resources (idempotent whole-season reload).

    The season-grain Jolpica endpoints return the whole season at once, so this
    replaces the current season's rows. For the per-round FastF1/Ergast sources
    (laps, telemetry, positions, pit stops, ...) use their own `--incremental`
    flag, which loads only rounds past the high-watermark.
    """
    configure_logging()
    current_season = get_settings().current_season
    res = tuple(resources) if resources else DEFAULT_RESOURCES
    log.info("cli.incremental.start", season=current_season, resources=res)
    summary = run_backfill([current_season], res)
    _print_summary(summary)


@app.command()
def health(
    season: Annotated[
        int | None,
        typer.Option(help="Season to inspect; default = configured current season."),
    ] = None,
    max_age_hours: Annotated[
        float,
        typer.Option(help="Maximum age of the latest audited successful load."),
    ] = 192.0,
    require_resource: Annotated[
        list[str] | None,
        typer.Option(
            "--require-resource",
            help="Additional audited resource to require; repeatable (for heavy sources).",
        ),
    ] = None,
    record: Annotated[
        bool,
        typer.Option("--record/--no-record", help="Append results to ops health history."),
    ] = True,
) -> None:
    """Fail unless the persistent pipeline has fresh, non-empty core loads."""
    configure_logging()
    settings = get_settings()
    required = require_resource if require_resource is not None else None
    checks = evaluate_pipeline_health(
        settings,
        season=season,
        max_age_hours=max_age_hours,
        required_resources=required,
    )
    for check in checks:
        marker = "PASS" if check.passed else "FAIL"
        typer.echo(f"{marker:<4} {check.name}: {check.detail}")
    if record:
        record_pipeline_health(checks, settings, season=season)
    if not all(check.passed for check in checks):
        raise typer.Exit(code=1)


@app.command("backup-postgres")
def backup_postgres(
    directory: Annotated[
        Path, typer.Option(help="Directory for the dump and checksum manifest.")
    ] = Path("data/backups"),
) -> None:
    """Create an atomic, checksummed PostgreSQL backup."""
    configure_logging()
    backup = create_postgres_backup(directory)
    typer.echo(f"Created {backup} and {backup.with_suffix('.dump.json')}.")


@app.command("restore-drill")
def restore_drill(
    backup: Annotated[Path, typer.Option(exists=True, dir_okay=False, help="Dump to test.")],
) -> None:
    """Restore a backup into an isolated temporary database and remove it."""
    configure_logging()
    audit_rows = run_postgres_restore_drill(backup)
    typer.echo(f"Restore drill passed ({audit_rows} ingestion audit rows).")


@app.command("restore-drill-latest")
def restore_drill_latest(
    directory: Annotated[
        Path, typer.Option(exists=True, file_okay=False, help="Directory containing dumps.")
    ] = Path("data/backups"),
) -> None:
    """Run an isolated restore drill against the newest timestamped backup."""
    configure_logging()
    backup = latest_postgres_backup(directory)
    audit_rows = run_postgres_restore_drill(backup)
    typer.echo(f"Restore drill passed for {backup} ({audit_rows} ingestion audit rows).")


@app.command("restore-partition")
def restore_partition(
    resource: Annotated[str, typer.Option(help="Raw resource/table name.")],
    season: Annotated[int, typer.Option(help="Season partition to restore.")],
    round_: Annotated[
        int | None,
        typer.Option("--round", help="Round to restore; omit for a season-grain resource."),
    ] = None,
) -> None:
    """Restore one warehouse partition from the lake without refetching it."""
    configure_logging()
    rows = restore_lake_partition(resource, season, round_=round_)
    grain = f"season {season}" if round_ is None else f"season {season}, round {round_}"
    typer.echo(f"Restored {rows} {resource} rows for {grain}.")


@app.command()
def laps(
    season: Annotated[int, typer.Option(help="Season to load FastF1 laps for.")],
    from_round: FromRoundOpt = 1,
    to_round: ToRoundOpt = None,
    session: SessionOpt = "R",
    incremental: IncrementalOpt = False,
) -> None:
    """Ingest FastF1 per-lap timing/tyre data (requires the `telemetry` extra)."""
    configure_logging()
    rounds = _resolve_rounds(season, from_round, to_round, incremental=incremental, table="laps")
    if not rounds:
        typer.echo(f"{season}: laps already up to date — nothing new to load.")
        return
    log.info("cli.laps.start", season=season, rounds=rounds, session=session)
    rows = ingest_laps(season, rounds, session)
    _echo_rounds(rows, season, rounds, "laps", f" ({session})")


@app.command()
def pitstops(
    season: Annotated[int, typer.Option(help="Season to load Ergast pit stops for.")],
    from_round: FromRoundOpt = 1,
    to_round: ToRoundOpt = None,
    incremental: IncrementalOpt = False,
) -> None:
    """Ingest Ergast pit-stop timing (per round; needs `races` backfilled for auto rounds)."""
    configure_logging()
    rounds = _resolve_rounds(
        season, from_round, to_round, incremental=incremental, table="pitstops"
    )
    if not rounds:
        typer.echo(f"{season}: pit stops already up to date — nothing new to load.")
        return
    log.info("cli.pitstops.start", season=season, rounds=rounds)
    rows = ingest_pitstops(season, rounds)
    _echo_rounds(rows, season, rounds, "pit stops")


@app.command()
def weather(
    season: Annotated[int, typer.Option(help="Season to load FastF1 weather for.")],
    from_round: FromRoundOpt = 1,
    to_round: ToRoundOpt = None,
    session: SessionOpt = "R",
    incremental: IncrementalOpt = False,
) -> None:
    """Ingest FastF1 per-minute weather (requires the `telemetry` extra)."""
    configure_logging()
    rounds = _resolve_rounds(season, from_round, to_round, incremental=incremental, table="weather")
    if not rounds:
        typer.echo(f"{season}: weather already up to date — nothing new to load.")
        return
    log.info("cli.weather.start", season=season, rounds=rounds, session=session)
    rows = ingest_weather(season, rounds, session)
    _echo_rounds(rows, season, rounds, "weather rows")


@app.command("ergast-laps")
def ergast_laps(
    season: Annotated[int, typer.Option(help="Season to load Ergast lap positions for.")],
    from_round: FromRoundOpt = 1,
    to_round: ToRoundOpt = None,
    incremental: IncrementalOpt = False,
) -> None:
    """Ingest Ergast per-lap position/time (per round; powers the pit-strategy mart)."""
    configure_logging()
    rounds = _resolve_rounds(
        season, from_round, to_round, incremental=incremental, table="ergast_laps"
    )
    if not rounds:
        typer.echo(f"{season}: ergast laps already up to date — nothing new to load.")
        return
    log.info("cli.ergast_laps.start", season=season, rounds=rounds)
    rows = ingest_ergast_laps(season, rounds)
    _echo_rounds(rows, season, rounds, "lap records")


@app.command()
def telemetry(
    season: Annotated[int, typer.Option(help="Season to load FastF1 telemetry for.")],
    from_round: FromRoundOpt = 1,
    to_round: ToRoundOpt = None,
    session: SessionOpt = "R",
    incremental: IncrementalOpt = False,
    fastest_only: FastestOnlyOpt = False,
) -> None:
    """Ingest FastF1 distance-resampled telemetry (heavy; requires `telemetry` extra)."""
    configure_logging()
    rounds = _resolve_rounds(
        season, from_round, to_round, incremental=incremental, table="telemetry"
    )
    if not rounds:
        typer.echo(f"{season}: telemetry already up to date — nothing new to load.")
        return
    log.info(
        "cli.telemetry.start",
        season=season,
        rounds=rounds,
        session=session,
        fastest_only=fastest_only,
    )
    rows = ingest_telemetry(season, rounds, session, fastest_only=fastest_only)
    _echo_rounds(rows, season, rounds, "telemetry rows")


@app.command()
def positions(
    season: Annotated[int, typer.Option(help="Season to load FastF1 positions for.")],
    from_round: FromRoundOpt = 1,
    to_round: ToRoundOpt = None,
    session: SessionOpt = "R",
    incremental: IncrementalOpt = False,
) -> None:
    """Ingest FastF1 time-stamped car positions for the replay map (heavy; `telemetry` extra)."""
    configure_logging()
    rounds = _resolve_rounds(
        season, from_round, to_round, incremental=incremental, table="positions"
    )
    if not rounds:
        typer.echo(f"{season}: positions already up to date — nothing new to load.")
        return
    log.info("cli.positions.start", season=season, rounds=rounds, session=session)
    rows = ingest_positions(season, rounds, session)
    _echo_rounds(rows, season, rounds, "position rows")


@app.command("race-control")
def race_control(
    season: Annotated[int, typer.Option(help="Season to load FastF1 race-control messages for.")],
    from_round: FromRoundOpt = 1,
    to_round: ToRoundOpt = None,
    session: SessionOpt = "R",
    incremental: IncrementalOpt = False,
) -> None:
    """Ingest FastF1 race-control messages (flags/SC/penalties; needs `telemetry` extra)."""
    configure_logging()
    rounds = _resolve_rounds(
        season, from_round, to_round, incremental=incremental, table="race_control"
    )
    if not rounds:
        typer.echo(f"{season}: race-control already up to date — nothing new to load.")
        return
    log.info("cli.race_control.start", season=season, rounds=rounds, session=session)
    rows = ingest_race_control(season, rounds, session)
    _echo_rounds(rows, season, rounds, "race-control messages")


@app.command("team-radio")
def team_radio(
    season: Annotated[int, typer.Option(help="Season to load OpenF1 team-radio clips for.")],
    from_round: FromRoundOpt = 1,
    to_round: ToRoundOpt = None,
    session: SessionOpt = "R",
    incremental: IncrementalOpt = False,
) -> None:
    """Ingest OpenF1 team-radio clips (audio; aligned via the telemetry cache)."""
    configure_logging()
    rounds = _resolve_rounds(
        season, from_round, to_round, incremental=incremental, table="team_radio"
    )
    if not rounds:
        typer.echo(f"{season}: team radio already up to date — nothing new to load.")
        return
    log.info("cli.team_radio.start", season=season, rounds=rounds, session=session)
    rows = ingest_team_radio(season, rounds, session)
    _echo_rounds(rows, season, rounds, "team-radio clips")


@app.command("openf1-timing")
def openf1_timing(
    season: Annotated[int, typer.Option(help="Season to load OpenF1 timing evidence for.")],
    from_round: FromRoundOpt = 1,
    to_round: ToRoundOpt = None,
    session: SessionOpt = "R",
    incremental: IncrementalOpt = False,
) -> None:
    """Ingest aligned OpenF1 positions, intervals and race-control evidence."""
    configure_logging()
    rounds = _resolve_rounds(
        season, from_round, to_round, incremental=incremental, table="openf1_timing_audit"
    )
    if not rounds:
        typer.echo(f"{season}: OpenF1 timing already up to date — nothing new to load.")
        return
    log.info("cli.openf1_timing.start", season=season, rounds=rounds, session=session)
    rows = ingest_openf1_timing(season, rounds, session)
    _echo_rounds(rows, season, rounds, "OpenF1 timing rows")


if __name__ == "__main__":
    app()
