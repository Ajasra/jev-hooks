"""Compatibility tests for the legacy Antigravity safety entry point."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
GATE = [sys.executable, str(ROOT / ".agents/hooks/jev_safety_gate.py")]


def run_gate(tmp_path: Path, command: str) -> dict:
    env = dict(os.environ)
    env["JEV_DATA_ROOT"] = str(tmp_path / "data")
    env.pop("TYPESAFE_API_KEY", None)
    env.pop("OPENROUTER_API_KEY", None)
    payload = {
        "hookEventName": "PreToolUse",
        "conversationId": "legacy-test",
        "invocationId": command,
        "workspacePaths": [str(ROOT)],
        "toolCall": {"name": "run_command", "args": {"CommandLine": command}},
    }
    completed = subprocess.run(
        GATE,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
        timeout=10,
        check=True,
    )
    return json.loads(completed.stdout)


def test_legacy_entry_allows_routine_command(tmp_path: Path):
    assert run_gate(tmp_path, "cmd /c git status")["decision"] == "allow"


def test_legacy_entry_denies_invariant(tmp_path: Path):
    assert run_gate(tmp_path, "cmd /c git reset --hard HEAD~1")["decision"] == "deny"
