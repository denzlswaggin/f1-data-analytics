"""Credential-safe delivery of operational alerts to a generic webhook."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from ingestion.config import Settings, get_settings


class AlertDeliveryError(RuntimeError):
    """Raised when a configured alert endpoint rejects or cannot receive an alert."""


def send_webhook_alert(
    event: str,
    message: str,
    *,
    severity: str = "error",
    attributes: Mapping[str, Any] | None = None,
    settings: Settings | None = None,
) -> bool:
    """POST a portable JSON alert, returning ``False`` when no webhook is configured."""
    settings = settings or get_settings()
    url = settings.alert_webhook_url.strip()
    if not url:
        return False
    if urlparse(url).scheme not in {"http", "https"}:
        raise AlertDeliveryError("alert webhook must use http or https")

    payload = json.dumps(
        {
            "event": event,
            "severity": severity,
            "message": message,
            "attributes": dict(attributes or {}),
        },
        default=str,
    ).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "f1-data-platform/1"}
    token = settings.alert_webhook_bearer_token.get_secret_value()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(
            request, timeout=settings.alert_webhook_timeout_seconds
        ) as response:
            status = response.status
    except (OSError, urllib.error.URLError) as exc:
        raise AlertDeliveryError(f"alert webhook request failed: {exc}") from exc
    if not 200 <= status < 300:
        raise AlertDeliveryError(f"alert webhook returned HTTP {status}")
    return True
