"""Small HTTP boundary for TypeSafe System One requests."""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol


def _load_env_defaults() -> None:
    candidates = [
        Path(".agents/.env"),
        Path(".env"),
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
                        if k and k not in os.environ:
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
                "https://openrouter.ai/api/v1/systemone"
                if is_openrouter
                else "https://api.typesafe.ai/v1/systemone"
            )
        model = os.environ.get("JEV_MODEL", "").strip() or (
            "typesafe/jev-1.13" if is_openrouter else "jev-latest"
        )
        return cls(key, endpoint, model)

    def evaluate(self, state: Any, questions: Mapping[str, Any], timeout: float) -> dict[str, Any]:
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
        return dict(value.get("answers", {}))

