"""Common adapter helpers; no feature policy belongs here."""

from __future__ import annotations

import hashlib
import json
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Mapping

from jev.contracts import Event, Harness, Operation, Result


def workspace_id(cwd: str) -> str:
    normalized = str(Path(cwd).resolve()).casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


def stable_event_id(parts: tuple[str, ...], raw: Mapping[str, Any]) -> str:
    meaningful = "\x1f".join(parts)
    if not meaningful.strip("\x1f"):
        meaningful = json.dumps(raw, sort_keys=True, default=str)
    return hashlib.sha256(meaningful.encode("utf-8")).hexdigest()[:32]


def patch_paths(patch: str) -> tuple[str, ...]:
    paths: list[str] = []
    for match in re.finditer(r"(?m)^\*\*\* (?:Add|Update|Delete) File:\s*(.+?)\s*$", patch):
        paths.append(match.group(1).strip())
    return tuple(paths)


def extract_turn_context(transcript_path: str | Path | None) -> dict[str, str]:
    if not transcript_path:
        return {}
    path = Path(transcript_path)
    if not path.exists():
        return {}
    current_prompt = ""
    prior_prompt = ""
    found_current = False
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                step = json.loads(line)
            except Exception:
                continue
            is_user = step.get("type") in {"USER_INPUT", "user"} or step.get("source") in {"USER_EXPLICIT", "user"}
            content = step.get("content", "")
            if not content and isinstance(step.get("message"), Mapping):
                content = step["message"].get("content", "")
            if not isinstance(content, str) or not content.strip():
                continue

            clean = content
            if "<USER_REQUEST>" in clean:
                match = re.search(r"<USER_REQUEST>(.*?)</USER_REQUEST>", clean, re.DOTALL)
                if match:
                    clean = match.group(1).strip()
            clean = clean.strip()

            if is_user and not found_current:
                found_current = True
                current_prompt = clean
                continue
            if is_user and found_current and not prior_prompt:
                prior_prompt = clean
                break
    except Exception:
        pass
    return {"current_prompt": current_prompt, "prior_prompt": prior_prompt}


class Adapter(ABC):
    harness: Harness

    @abstractmethod
    def decode(self, raw: Mapping[str, Any]) -> tuple[Event, Operation | None]:
        raise NotImplementedError

    @abstractmethod
    def encode(self, event: Event, result: Result) -> dict[str, Any]:
        raise NotImplementedError

    def _deadline(self, seconds: float = 0.30) -> float:
        return time.monotonic() + seconds

