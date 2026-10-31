from __future__ import annotations

import threading
import time

import pytest

from jev.services.client import HttpDecisionClient


@pytest.fixture(autouse=True)
def isolated_request_slots(monkeypatch):
    monkeypatch.setattr("jev.services.client._REQUEST_SLOTS", threading.BoundedSemaphore(4))


def test_elapsed_deadline_includes_stalled_connection_setup(monkeypatch):
    release = threading.Event()
    started = threading.Event()

    def stalled(*args, **kwargs):
        started.set()
        release.wait(2)
        return {}

    monkeypatch.setattr(HttpDecisionClient, "_request", stalled)
    client = HttpDecisionClient("fixture", "http://fixture.invalid", "fixture")
    before = time.monotonic()
    try:
        with pytest.raises(TimeoutError):
            client.evaluate({}, {}, 0.03)
        assert started.is_set()
        assert time.monotonic() - before < 0.3
    finally:
        release.set()


def test_provider_errors_and_success_are_preserved(monkeypatch):
    client = HttpDecisionClient("fixture", "http://fixture.invalid", "fixture")
    monkeypatch.setattr(HttpDecisionClient, "_request", lambda *args: {"routine": {"noul": 0.9}})
    assert client.evaluate({}, {}, 0.2) == {"routine": {"noul": 0.9}}

    def failed(*args):
        raise ValueError("provider unavailable")

    monkeypatch.setattr(HttpDecisionClient, "_request", failed)
    with pytest.raises(ValueError, match="provider unavailable"):
        client.evaluate({}, {}, 0.2)
