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
    session_objective = ""
    active_file = ""
    last_error = ""
    found_current = False
    try:
        raw_lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        # Find session objective from first non-empty user input
        for line in raw_lines:
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
            if is_user and isinstance(content, str) and content.strip():
                clean = content
                if "<USER_REQUEST>" in clean:
                    match = re.search(r"<USER_REQUEST>(.*?)</USER_REQUEST>", clean, re.DOTALL)
                    if match:
                        clean = match.group(1).strip()
                session_objective = clean.strip()[:300]
                break

        # Scan backwards for current/prior prompts, active file, and last error
        for line in reversed(raw_lines):
            if not line.strip():
                continue
            try:
                step = json.loads(line)
            except Exception:
                continue

            # Check for active file
            if not active_file:
                tool_calls = step.get("tool_calls") or []
                for tc in tool_calls:
                    args = tc.get("args") or {}
                    cand = str(args.get("TargetFile") or args.get("file_path") or args.get("path") or "")
                    if cand:
                        active_file = cand
                        break

            # Check for recent error
            if not last_error:
                status = str(step.get("status") or "")
                if status in {"ERROR", "error", "failed"}:
                    last_error = str(step.get("content") or step.get("message") or "")[:400]
                elif "error" in str(step.get("content", "")).lower()[:200]:
                    last_error = str(step.get("content", ""))[:400]

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

            if found_current and prior_prompt and active_file and last_error:
                break
    except Exception:
        pass
    return {
        "current_prompt": current_prompt,
        "prior_prompt": prior_prompt,
        "session_objective": session_objective,
        "active_file": active_file,
        "last_error": last_error,
    }


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

