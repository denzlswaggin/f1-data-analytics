"""Offline tests for the Jolpica client's pagination and retry behaviour."""

from __future__ import annotations

from typing import Any

import pytest
from ingestion.clients.jolpica import JolpicaClient, RetryableJolpicaError
from ingestion.config import Settings


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.headers: dict[str, str] = {}

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise AssertionError(f"unexpected status {self.status_code}")


def _page(total: int, offset: int, races: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "MRData": {
            "total": str(total),
            "limit": "100",
            "offset": str(offset),
            "RaceTable": {"Races": races},
        }
    }


def _fast_client() -> JolpicaClient:
    # Disable throttling for a fast offline test.
    return JolpicaClient(Settings(jolpica_rate_limit_per_sec=100000))


def test_paginate_follows_offset_until_total(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _fast_client()
    pages = [
        _page(150, 0, [{"round": str(i)} for i in range(100)]),
        _page(150, 100, [{"round": str(i)} for i in range(100, 150)]),
    ]
    calls: list[dict[str, Any]] = []

    def fake_get(url: str, params: dict[str, Any], timeout: int) -> _FakeResponse:
        calls.append(dict(params))
        return _FakeResponse(200, pages[params["offset"] // 100])

    monkeypatch.setattr(client._session, "get", fake_get)

    records = list(client.paginate("2023/results", "RaceTable", "Races"))
    assert len(records) == 150
    assert [c["offset"] for c in calls] == [0, 100]


def test_retryable_error_on_server_fault(monkeypatch: pytest.MonkeyPatch) -> None:
    client = JolpicaClient(Settings(jolpica_rate_limit_per_sec=100000, jolpica_max_retries=0))

    def fake_get(url: str, params: dict[str, Any], timeout: int) -> _FakeResponse:
        return _FakeResponse(503)

    monkeypatch.setattr(client._session, "get", fake_get)

    with pytest.raises(RetryableJolpicaError):
        list(client.paginate("2023/results", "RaceTable", "Races"))
