"""Tests for OpenF1 authentication and response handling."""

from typing import Any
from unittest.mock import Mock, call

import pytest
from ingestion.clients.openf1 import OpenF1AuthenticationError, OpenF1Client


def _response(status_code: int, payload: object) -> Any:
    response = Mock()
    response.status_code = status_code
    response.json.return_value = payload
    return response


def test_access_token_is_added_to_requests() -> None:
    client = OpenF1Client(access_token="test-token")

    assert client._session.headers["Authorization"] == "Bearer test-token"


def test_client_authenticates_and_retries_after_unauthorized_response() -> None:
    client = OpenF1Client(
        base_url="https://example.test/v1",
        min_interval_s=0,
        username="driver@example.test",
        password="secret",
    )
    session: Any = Mock()
    session.get.side_effect = [
        _response(401, {"detail": "restricted"}),
        _response(200, [{"session_key": 123}]),
    ]
    session.post.return_value = _response(200, {"access_token": "fresh-token"})
    client._session = session

    assert client.race_sessions(2026) == [{"session_key": 123}]
    assert session.get.call_args_list == [
        call(
            "https://example.test/v1/sessions",
            params={"year": 2026, "session_name": "Race"},
            timeout=30,
        ),
        call(
            "https://example.test/v1/sessions",
            params={"year": 2026, "session_name": "Race"},
            timeout=30,
        ),
    ]
    session.post.assert_called_once_with(
        "https://example.test/token",
        data={"username": "driver@example.test", "password": "secret"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    session.headers.update.assert_called_once_with({"Authorization": "Bearer fresh-token"})


def test_client_explains_live_session_restriction_without_credentials() -> None:
    client = OpenF1Client(base_url="https://example.test/v1", min_interval_s=0)
    session: Any = Mock()
    session.get.return_value = _response(401, {"detail": "restricted"})
    client._session = session

    with pytest.raises(OpenF1AuthenticationError, match="F1_OPENF1_USERNAME"):
        client.race_sessions(2026)
