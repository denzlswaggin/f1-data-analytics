"""Backfill does not request seasons outside the published data context."""

from __future__ import annotations

from ingestion.cli import app
from typer.testing import CliRunner


def test_backfill_rejects_old_season_without_ingesting() -> None:
    result = CliRunner().invoke(app, ["backfill", "--season", "2023"])

    assert result.exit_code != 0
    assert "2024-2026" in result.output


def test_backfill_rejects_future_season_without_ingesting() -> None:
    result = CliRunner().invoke(app, ["backfill", "--from", "2024", "--to", "2027"])

    assert result.exit_code != 0
    assert "2024-2026" in result.output
