from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("harness", ["codex", "antigravity", "opencode"])
def test_worker_preserves_harness_contract_and_recovers_from_bad_request(tmp_path: Path, harness: str):
    args = {"command": "git reset --hard HEAD~1"}
    if harness == "codex":
        payload = {"hook_event_name": "PreToolUse", "cwd": str(tmp_path), "session_id": "worker",
                   "tool_use_id": "call", "tool_name": "Bash", "tool_input": args}
    elif harness == "antigravity":
        payload = {"hookEventName": "PreToolUse", "cwd": str(tmp_path), "conversationId": "worker",
                   "invocationId": "call", "toolCall": {"name": "run_command", "args": args}}
    else:
        payload = {"hook": "tool.execute.before", "cwd": str(tmp_path), "session_id": "worker",
                   "tool": {"name": "bash", "call_id": "call", "args": args}}
    requests = [{"request_id": 1, "payload": []}, {"request_id": 2, "payload": payload}]
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"),
               JEV_DATA_ROOT=str(tmp_path / "data"), TYPESAFE_API_KEY="", OPENROUTER_API_KEY="")
    process = subprocess.run([sys.executable, "-u", "-m", "jev", "hook-worker", "--harness", harness],
                             input="".join(json.dumps(item) + "\n" for item in requests),
                             text=True, capture_output=True, env=env, timeout=10)
    assert process.returncode == 0, process.stderr
    ready, error, reply = [json.loads(line) for line in process.stdout.splitlines()]
    assert ready == {"ready": True}
    assert error == {"request_id": 1, "error": "ValueError"}
    assert reply["request_id"] == 2
    output = reply["result"]
    if harness == "codex":
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
    else:
        assert output["decision"] == "deny"


def test_worker_preserves_utf8_context_on_windows(tmp_path: Path):
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"),
               JEV_DATA_ROOT=str(tmp_path / "data"), TYPESAFE_API_KEY="", OPENROUTER_API_KEY="")
    common = {"cwd": str(tmp_path), "session_id": "utf8"}
    requests = [
        {"request_id": 1, "payload": {**common, "hook": "chat.message", "prompt": "修复共享运行时"}},
        {"request_id": 2, "payload": {**common, "hook": "experimental.session.compacting"}},
    ]
    process = subprocess.run([sys.executable, "-u", "-m", "jev", "hook-worker", "--harness", "opencode"],
                             input="".join(json.dumps(item, ensure_ascii=False) + "\n" for item in requests),
                             encoding="utf-8", capture_output=True, env=env, timeout=10)
    assert process.returncode == 0, process.stderr
    reply = json.loads(process.stdout.splitlines()[-1])
    assert "修复共享运行时" in reply["result"]["checkpoint_context"][0]
