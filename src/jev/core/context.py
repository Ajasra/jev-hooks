"""Context Envelope and Multi-Modal State Assembly (RFC-26)."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from jev.contracts import Event
from jev.services.storage import redact


@dataclass(frozen=True)
class ContextEnvelope:
    prompt: str
    active_path: str = ""
    git_branch: str = ""
    git_status_summary: str = ""
    prior_context: str = ""
    last_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_semantic_string(self) -> str:
        """Renders a compact, high-signal prompt representation capped at 4,000 chars."""
        clean_prompt = self.prompt.strip()
        if not (self.active_path or self.git_branch or self.git_status_summary or self.last_error):
            return clean_prompt

        parts: list[str] = [clean_prompt]
        if self.active_path:
            parts.append(f"Active file: {self.active_path.strip()}")
        if self.git_branch:
            parts.append(f"Branch: {self.git_branch.strip()}")
        if self.git_status_summary:
            parts.append(f"Uncommitted changes:\n{self.git_status_summary.strip()[:600]}")
        if self.last_error:
            parts.append(f"Recent error:\n{self.last_error.strip()[:500]}")
        if self.prior_context:
            parts.append(f"Prior context:\n{self.prior_context.strip()[:500]}")

        full_text = "\n\n".join(parts)
        return full_text[:4000]


def _git_branch(cwd: Path) -> str:
    """Fast, safe resolution of current git branch."""
    try:
        process = subprocess.run(
            ["git", "-c", f"safe.directory={cwd.as_posix()}", "branch", "--show-current"],
            cwd=str(cwd), capture_output=True, text=True, timeout=0.15,
            encoding="utf-8", errors="replace",
        )
        if process.returncode == 0 and process.stdout.strip():
            return process.stdout.strip()
        process = subprocess.run(
            ["git", "-c", f"safe.directory={cwd.as_posix()}", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(cwd), capture_output=True, text=True, timeout=0.15,
            encoding="utf-8", errors="replace",
        )
        if process.returncode == 0:
            branch = process.stdout.strip()
            return branch if branch != "HEAD" else ""
    except Exception:
        pass
    return ""


def _git_status_summary(cwd: Path) -> str:
    """Fast, bounded extraction of short git status."""
    try:
        process = subprocess.run(
            ["git", "-c", f"safe.directory={cwd.as_posix()}", "status", "--short"],
            cwd=str(cwd), capture_output=True, text=True, timeout=0.15,
            encoding="utf-8", errors="replace",
        )
        if process.returncode == 0 and process.stdout:
            lines = [line.strip() for line in process.stdout.splitlines() if line.strip()]
            return "\n".join(lines[:10])
    except Exception:
        pass
    return ""


def _extract_recent_error_and_file(transcript_path: str | Path | None) -> tuple[str, str]:
    """Inspects recent transcript steps for failing tool outputs or active files."""
    if not transcript_path:
        return "", ""
    path = Path(transcript_path)
    if not path.exists():
        return "", ""

    last_error = ""
    active_file = ""

    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in reversed(lines[-25:]):
            if not line.strip():
                continue
            try:
                step = json.loads(line)
            except Exception:
                continue

            # Look for active file references
            if not active_file:
                tool_calls = step.get("tool_calls") or []
                for tc in tool_calls:
                    args = tc.get("args") or {}
                    cand = str(args.get("TargetFile") or args.get("file_path") or args.get("path") or "")
                    if cand:
                        active_file = cand
                        break

            # Look for recent errors
            if not last_error:
                status = str(step.get("status") or "")
                if status in {"ERROR", "error", "failed"}:
                    last_error = str(step.get("content") or step.get("message") or "")[:400]
                elif "error" in str(step.get("content", "")).lower()[:200]:
                    last_error = str(step.get("content", ""))[:400]

            if active_file and last_error:
                break
    except Exception:
        pass

    return last_error, active_file


def assemble_envelope(event: Event, cwd: Path | None = None) -> ContextEnvelope:
    """Assembles a high-signal, bounded 4-layer Context Envelope from event and environment."""
    workspace = cwd or Path(event.cwd)
    payload = event.payload

    prompt = str(payload.get("prompt") or "")
    prior_context = str(payload.get("prior_context") or "")
    transcript_path = str(payload.get("transcript_path") or "")

    last_error, active_file = _extract_recent_error_and_file(transcript_path)

    # Allow payload overrides if present
    if payload.get("active_path"):
        active_file = str(payload["active_path"])
    if payload.get("last_error"):
        last_error = str(payload["last_error"])

    git_branch = _git_branch(workspace)
    git_status = _git_status_summary(workspace)

    return ContextEnvelope(
        prompt=redact(prompt, 1500),
        active_path=redact(active_file, 500),
        git_branch=git_branch,
        git_status_summary=redact(git_status, 800),
        prior_context=redact(prior_context, 1000),
        last_error=redact(last_error, 800),
    )
