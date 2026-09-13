from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import requests
from scripts.capture_openf1_reference import capture
from scripts.compare_openf1_orders import load_capture


def fake_client(monkeypatch: pytest.MonkeyPatch, failure: str | None = None) -> None:
    client = MagicMock()
    client.__enter__.return_value = client

    def get(url: str, params: dict[str, int], timeout: int) -> requests.Response:
        row: dict[str, Any] = {**params}
        payload: Any = [row]
        status = 200
        if failure == "forbidden":
            status = 403
        elif failure == "malformed":
            payload = {"error": "Not an event list"}
        elif failure == "wrong_session":
            row["session_key"] = 999
        elif failure == "wrong_driver" and "driver_number" in params:
            row["driver_number"] = 999
        response = requests.Response()
        response.status_code = status
        response._content = json.dumps(payload).encode()
        response.url = url
        return response

    client.get.side_effect = get
    monkeypatch.setattr("scripts.capture_openf1_reference.requests.Session", lambda: client)
    monkeypatch.setattr("scripts.capture_openf1_reference.time.sleep", lambda _: None)


def test_capture_preserves_response_bytes_and_cannot_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_client(monkeypatch)
    output = tmp_path / "capture"
    manifest = capture(123, [4, 81], output)
    assert len(manifest["files"]) == 6
    for item in manifest["files"]:
        assert item["sha256"] == hashlib.sha256((output / item["file"]).read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        capture(123, [4, 81], output)


@pytest.mark.parametrize("failure", ["forbidden", "malformed", "wrong_session", "wrong_driver"])
def test_failed_capture_never_publishes_a_complete_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    fake_client(monkeypatch, failure)
    output = tmp_path / "capture"
    with pytest.raises((requests.HTTPError, ValueError)):
        capture(123, [4, 81], output)
    assert not (output / "manifest.json").exists()


def test_interval_capture_requires_both_hashed_streams(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_client(monkeypatch)
    output = tmp_path / "capture"
    capture(123, [4, 81], output, include_intervals=True)
    manifest, data = load_capture(output)
    assert manifest["schema_version"] == 2
    assert len(data) == 8
    (output / "intervals-4.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="integrity"):
        load_capture(output)
