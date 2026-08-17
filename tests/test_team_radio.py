"""Test for the pure team-radio helpers (no network needed)."""

from __future__ import annotations

from ingestion.pipeline import _code_from_radio_url


def test_code_from_radio_url_extracts_driver_code() -> None:
    url = "https://livetiming.formula1.com/static/2026/2026-05-24_Canadian_Grand_Prix/2026-05-24_Race/TeamRadio/NOR_1_20260524_124627.mp3"
    assert _code_from_radio_url(url) == "NOR"
    assert _code_from_radio_url("https://x/TeamRadio/RUS_63_20260523_160721.mp3") == "RUS"


def test_code_from_radio_url_returns_none_when_absent() -> None:
    assert _code_from_radio_url("https://example.com/no_team_radio_here.mp3") is None
    assert _code_from_radio_url(None) is None
