"""Webhook alert delivery tests with no external network access."""

from __future__ import annotations

import json
import urllib.request
from types import TracebackType
from typing import Any, cast

import pytest
from ingestion.alerts import AlertDeliveryError, send_webhook_alert
from ingestion.config import Settings
from pydantic import SecretStr


class _Response:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> _Response:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


def test_unconfigured_webhook_is_a_noop() -> None:
    assert not send_webhook_alert("test", "message", settings=Settings())


def test_webhook_posts_portable_json_with_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _Response:
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response(202)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    settings = Settings(
        alert_webhook_url="https://alerts.example.test/events",
        alert_webhook_bearer_token=SecretStr("secret-token"),
        alert_webhook_timeout_seconds=3,
    )

    assert send_webhook_alert(
        "dagster.run_failed",
        "pipeline failed",
        attributes={"run_id": "abc"},
        settings=settings,
    )
    request = captured["request"]
    assert isinstance(request, urllib.request.Request)
    assert request.get_header("Authorization") == "Bearer secret-token"
    assert json.loads(cast(bytes, request.data or b"{}"))["attributes"] == {"run_id": "abc"}
    assert captured["timeout"] == 3


def test_webhook_rejects_unsupported_url_scheme() -> None:
    settings = Settings(alert_webhook_url="file:///tmp/alert")

    with pytest.raises(AlertDeliveryError, match="http or https"):
        send_webhook_alert("test", "message", settings=settings)
