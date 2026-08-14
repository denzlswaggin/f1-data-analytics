"""Client for the Jolpica-F1 API (the backwards-compatible Ergast successor).

Jolpica is volunteer-run and rate-limited, so this client:
  * throttles requests to a configurable requests/second budget,
  * retries transient failures (429 / 5xx / connection errors) with exponential
    backoff, honouring the ``Retry-After`` header when present,
  * transparently paginates Ergast's ``limit``/``offset`` responses.

The Ergast/Jolpica JSON envelope always looks like::

    {"MRData": {"total": "1234", "limit": "100", "offset": "0", "<X>Table": ...}}
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ingestion.config import Settings, get_settings
from ingestion.logging import get_logger

log = get_logger(__name__)

# Ergast/Jolpica caps page size at 100 records.
MAX_PAGE_LIMIT = 100


class RetryableJolpicaError(Exception):
    """Transient error worth retrying (rate limit or server-side fault)."""


class _RateLimiter:
    """Minimal single-process throttle enforcing a minimum request interval."""

    def __init__(self, requests_per_sec: float) -> None:
        self._min_interval = 1.0 / requests_per_sec if requests_per_sec > 0 else 0.0
        self._last = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last = time.monotonic()


class JolpicaClient:
    """Thin, polite HTTP client over the Jolpica-F1 (Ergast-compatible) API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.jolpica_base_url.rstrip("/")
        self._limiter = _RateLimiter(self.settings.jolpica_rate_limit_per_sec)
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": "f1-data-analytics/0.1 (+github.com/denzlswaggin)"}
        )

    # -- low-level ---------------------------------------------------------
    def _request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """Perform one rate-limited, retrying GET and return the MRData block."""

        @retry(
            retry=retry_if_exception_type(
                (RetryableJolpicaError, requests.ConnectionError, requests.Timeout)
            ),
            wait=wait_exponential(multiplier=1, min=1, max=30),
            stop=stop_after_attempt(self.settings.jolpica_max_retries + 1),
            reraise=True,
        )
        def _do() -> dict[str, Any]:
            self._limiter.wait()
            url = f"{self.base_url}/{path.lstrip('/')}"
            resp = self._session.get(url, params=params, timeout=30)

            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", "2"))
                log.warning("jolpica.rate_limited", url=url, retry_after=retry_after)
                time.sleep(retry_after)
                raise RetryableJolpicaError(f"429 rate limited on {url}")
            if resp.status_code >= 500:
                raise RetryableJolpicaError(f"{resp.status_code} server error on {url}")

            resp.raise_for_status()
            payload: dict[str, Any] = resp.json()
            mrdata: dict[str, Any] = payload["MRData"]
            return mrdata

        return _do()

    # -- pagination --------------------------------------------------------
    def paginate(
        self, path: str, table_key: str, list_key: str, params: dict[str, Any] | None = None
    ) -> Iterator[dict[str, Any]]:
        """Yield every record for an Ergast resource, following offset pages.

        ``table_key`` / ``list_key`` navigate the envelope, e.g. for results:
        ``table_key="RaceTable"``, ``list_key="Races"``.
        """
        params = dict(params or {})
        params["limit"] = MAX_PAGE_LIMIT
        offset = 0
        total = None

        while True:
            params["offset"] = offset
            mrdata = self._request(f"{path}.json", params)
            total = int(mrdata.get("total", 0))
            records = mrdata.get(table_key, {}).get(list_key, [])
            log.debug(
                "jolpica.page",
                path=path,
                offset=offset,
                fetched=len(records),
                total=total,
            )
            yield from records

            offset += MAX_PAGE_LIMIT
            if offset >= total or not records:
                break
