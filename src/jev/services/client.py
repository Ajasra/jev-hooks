"""Small HTTP boundary for TypeSafe System One requests."""

from __future__ import annotations

import json
import os
import queue
import threading
import urllib.request
import urllib.error
import socket
import ssl
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol


_REQUEST_SLOTS = threading.BoundedSemaphore(4)


def _load_env_defaults() -> None:
    config_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    candidates = [
        Path(".agents/.env"),
        Path(".env"),
        config_root / "jev" / ".env",
        Path.home() / ".gemini" / "config" / ".env",
    ]
    for p in candidates:
        if p.is_file():
            try:
                for line in p.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip("'\"")
                        if k and v and k not in os.environ:
                            os.environ[k] = v
            except OSError:
                pass


class DecisionClient(Protocol):
    def evaluate(self, state: Any, questions: Mapping[str, Any], timeout: float) -> dict[str, Any]: ...


@dataclass
class HttpDecisionClient:
    api_key: str
    endpoint: str
    model: str

    @classmethod
    def from_environment(cls) -> "HttpDecisionClient | None":
        _load_env_defaults()
        typesafe_key = os.environ.get("TYPESAFE_API_KEY", "").strip()
        openrouter_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        key = openrouter_key or typesafe_key
        if not key:
            return None
        is_openrouter = bool(openrouter_key or typesafe_key.startswith("sk-or-v1-"))
        endpoint = os.environ.get("TYPESAFE_ENDPOINT", "").strip()
        if not endpoint:
            endpoint = (
                "https://openrouter.ai/api/alpha/decisions"
                if is_openrouter
                else "https://api.typesafe.ai/v1/systemone"
            )
        model = os.environ.get("JEV_MODEL", "").strip() or (
            "typesafe/jev-1.14" if is_openrouter else "jev-latest"
        )
        return cls(key, endpoint, model)

    def evaluate(self, state: Any, questions: Mapping[str, Any], timeout: float) -> dict[str, Any]:
        """Enforce elapsed time even when DNS or TLS setup ignores socket timeouts."""
        slots = _REQUEST_SLOTS
        if timeout <= 0 or not slots.acquire(blocking=False):
            raise TimeoutError("Jev semantic request budget exhausted")
        replies: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

        def request() -> None:
            try:
                replies.put((True, self._request(state, questions, timeout)))
            except Exception as exc:
                replies.put((False, exc))
            finally:
                slots.release()

        worker = threading.Thread(target=request, name="jev-semantic-request", daemon=True)
        try:
            worker.start()
        except Exception:
            slots.release()
            raise
        try:
            succeeded, value = replies.get(timeout=timeout)
        except queue.Empty as exc:
            raise TimeoutError("Jev semantic request exceeded its elapsed-time budget") from exc
        if not succeeded:
            raise value
        return value

    def _request(self, state: Any, questions: Mapping[str, Any], timeout: float) -> dict[str, Any]:
        payload = {"model": self.model, "state": state, "questions": questions}
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        if "openrouter.ai" in self.endpoint:
            headers.update({"HTTP-Referer": "https://github.com/typesafe-ai/jev", "X-Title": "Jev Harness Runtime"})
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("answers"), dict):
            raise ValueError("Provider response is missing an answers object.")
        answers = value["answers"]
        if set(questions) - set(answers):
            raise ValueError("Provider response omitted requested answers.")
        return answers



def failure_details(exc: Exception) -> dict[str, Any]:
    """Classify provider failures without persisting URLs, headers or response bodies."""
    reason = getattr(exc, "reason", exc)
    timed_out = isinstance(reason, (TimeoutError, socket.timeout)) or "timed out" in str(reason).lower()
    category = (
        "timeout" if timed_out else
        "http" if isinstance(exc, urllib.error.HTTPError) else
        "tls" if isinstance(reason, ssl.SSLError) else
        "network" if isinstance(exc, urllib.error.URLError) else "invalid_response"
    )
    details = {"provider_status": "unavailable", "error_category": category, "timed_out": timed_out}
    if isinstance(exc, urllib.error.HTTPError):
        details["http_status"] = exc.code
    return details
