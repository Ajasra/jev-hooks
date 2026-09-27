from __future__ import annotations

import json
import subprocess
from pathlib import Path

from jev.contracts import Event, EventKind, Harness, Operation, Outcome
from jev.core.context import ContextEnvelope, assemble_envelope
from jev.runtime import Runtime
from jev.services.paths import Settings
from jev.services.storage import Storage


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)


def test_context_envelope_formatting():
    # Bare prompt formatting
    bare = ContextEnvelope(prompt="run tests")
    assert bare.to_semantic_string() == "run tests"

    # Enriched envelope formatting
    enriched = ContextEnvelope(
        prompt="fix the bug",
        active_path="src/auth.py",
        git_branch="feature/jwt",
        git_status_summary="M src/auth.py",
        last_error="AssertionError: Token expired",
        prior_context="user: login failed",
    )
    rendered = enriched.to_semantic_string()
    assert "fix the bug" in rendered
    assert "Active file: src/auth.py" in rendered
    assert "Branch: feature/jwt" in rendered
    assert "Uncommitted changes:" in rendered
    assert "Recent error:" in rendered
    assert len(rendered) <= 4000


def test_assemble_envelope_git_integration(tmp_path: Path):
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    test_file = tmp_path / "app.py"
    test_file.write_text("print('hello')\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "init")
    _git(tmp_path, "checkout", "-b", "feature/auth-guard")

    # Modify file to produce uncommitted diff
    test_file.write_text("print('hello world')\n", encoding="utf-8")

    event = Event(
        kind=EventKind.TURN_BEFORE,
        harness=Harness.ANTIGRAVITY,
        event_id="evt_env_1",
        workspace_id="ws_1",
        session_id="sess_1",
        cwd=str(tmp_path),
        payload={"prompt": "check changes", "active_path": "app.py"},
    )

    envelope = assemble_envelope(event, tmp_path)
    assert envelope.prompt == "check changes"
    assert envelope.active_path == "app.py"
    assert envelope.git_branch == "feature/auth-guard"
    assert "app.py" in envelope.git_status_summary


def test_assemble_envelope_transcript_inspection(tmp_path: Path):
    transcript = tmp_path / "transcript.jsonl"
    steps = [
        {
            "step_index": 1,
            "type": "PLANNER_RESPONSE",
            "tool_calls": [{"name": "replace_file_content", "args": {"TargetFile": "src/service.py"}}],
            "status": "DONE",
        },
        {
            "step_index": 2,
            "type": "PLANNER_RESPONSE",
            "status": "ERROR",
            "content": "TypeError: unsupported operand type(s)",
        },
    ]
    with transcript.open("w", encoding="utf-8") as f:
        for s in steps:
            f.write(json.dumps(s) + "\n")

    event = Event(
        kind=EventKind.TURN_BEFORE,
        harness=Harness.ANTIGRAVITY,
        event_id="evt_env_2",
        workspace_id="ws_1",
        session_id="sess_1",
        cwd=str(tmp_path),
        payload={"prompt": "fix error", "transcript_path": str(transcript)},
    )

    envelope = assemble_envelope(event, tmp_path)
    assert envelope.active_path == "src/service.py"
    assert "TypeError: unsupported operand" in envelope.last_error


def test_assemble_envelope_secret_redaction(tmp_path: Path):
    event = Event(
        kind=EventKind.TURN_BEFORE,
        harness=Harness.ANTIGRAVITY,
        event_id="evt_env_3",
        workspace_id="ws_1",
        session_id="sess_1",
        cwd=str(tmp_path),
        payload={"prompt": "api_key = secret123456789 in src/auth.py"},
    )
    envelope = assemble_envelope(event, tmp_path)
    assert "secret123456789" not in envelope.prompt
    assert "[REDACTED]" in envelope.prompt


def test_runtime_dispatch_uses_context_envelope(tmp_path: Path):
    store = Storage(tmp_path / "data/jev.sqlite3")
    settings = Settings.load(tmp_path)
    runtime = Runtime(settings, storage=store, client=None)

    event = Event(
        kind=EventKind.TURN_BEFORE,
        harness=Harness.ANTIGRAVITY,
        event_id="evt_env_4",
        workspace_id="ws_1",
        session_id="sess_1",
        cwd=str(tmp_path),
        payload={"prompt": "status update"},
    )

    result = runtime.dispatch(event)
    assert result.outcome == Outcome.ABSTAIN
