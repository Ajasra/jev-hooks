from __future__ import annotations

import json
from pathlib import Path

from jev.adapters.antigravity import AntigravityAdapter
from jev.adapters.codex import CodexAdapter
from jev.contracts import Event, EventKind, Harness, Operation, Outcome
from jev.core.verification import (
    evaluate_operation,
    evaluate_verification,
    extract_mutation_content,
)
from jev.runtime import Runtime
from jev.services.paths import Settings
from jev.services.storage import Storage
from jev.tooling import verify_output


class MockSupportedClient:
    def evaluate(self, state, questions, timeout):
        return {
            "method_supported_by_docs": {"noul": 0.96},
            "arguments_match_spec": {"noul": 0.92},
            "support_level": {"choice": "fully_supported"},
        }


class MockContradictedClient:
    def evaluate(self, state, questions, timeout):
        return {
            "method_supported_by_docs": {"noul": 0.12},
            "arguments_match_spec": {"noul": 0.20},
            "support_level": {"choice": "contradicted"},
        }


def test_extract_mutation_content_antigravity():
    op_replace = Operation(
        kind="file_mutation",
        tool_name="replace_file_content",
        arguments={
            "TargetFile": "src/client.py",
            "ReplacementContent": "def fetch_data(): pass",
        },
    )
    content, paths = extract_mutation_content(op_replace, Harness.ANTIGRAVITY)
    assert content == "def fetch_data(): pass"
    assert "src/client.py" in paths

    op_write = Operation(
        kind="file_mutation",
        tool_name="write_to_file",
        arguments={
            "TargetFile": "src/new_module.py",
            "CodeContent": "x = 42",
        },
    )
    content, paths = extract_mutation_content(op_write, Harness.ANTIGRAVITY)
    assert content == "x = 42"
    assert "src/new_module.py" in paths


def test_extract_mutation_content_codex():
    patch_text = (
        "*** Update File: src/service.py\n"
        "@@ -10,3 +10,4 @@\n"
        " existing_code()\n"
        "+client.start_session(auto_renew=True)\n"
    )
    op_patch = Operation(
        kind="file_mutation",
        tool_name="apply_patch",
        command=patch_text,
        arguments={"command": patch_text},
        paths=("src/service.py",),
    )
    content, paths = extract_mutation_content(op_patch, Harness.CODEX)
    assert "client.start_session(auto_renew=True)" in content
    assert "src/service.py" in paths


def test_evaluate_verification_supported():
    res = evaluate_verification(
        code_snippet="client.get_token()",
        reference_context="API Reference: client.get_token() retrieves current token.",
        client=MockSupportedClient(),
    )
    assert res["verified"] is True
    assert res["support_level"] == "fully_supported"
    assert res["method_supported"] >= 0.90
    assert res["advisory"] is None


def test_evaluate_verification_contradicted():
    res = evaluate_verification(
        code_snippet="client.refreshTokenWithScope('read')",
        reference_context="API Reference: refreshTokenWithScope is removed. Use client.refresh_token() instead.",
        client=MockContradictedClient(),
    )
    assert res["verified"] is False
    assert res["support_level"] == "contradicted"
    assert res["method_supported"] < 0.20
    assert res["advisory"] is not None
    assert "contradicted by reference documentation" in res["advisory"]


def test_evaluate_verification_fail_open_on_exception():
    class BrokenClient:
        def evaluate(self, state, questions, timeout):
            raise TimeoutError("Network timeout")

    res = evaluate_verification(
        code_snippet="foo()",
        reference_context="docs",
        client=BrokenClient(),
    )
    assert res["verified"] is True
    assert res["advisory"] is None
    assert "error" in res


def test_runtime_pre_tool_verification_advisory_antigravity(tmp_path: Path):
    store = Storage(tmp_path / "data/jev.sqlite3")
    settings = Settings.load(tmp_path)
    runtime = Runtime(settings, storage=store, client=MockContradictedClient())

    # Create dummy target file with some docstring context
    target = tmp_path / "service.py"
    target.write_text('"""Service module: only supports client.run()."""\n', encoding="utf-8")

    event = Event(
        kind=EventKind.TOOL_BEFORE,
        harness=Harness.ANTIGRAVITY,
        event_id="evt_ag_1",
        workspace_id="ws_1",
        session_id="sess_1",
        cwd=str(tmp_path),
    )
    op = Operation(
        kind="file_mutation",
        tool_name="replace_file_content",
        arguments={
            "TargetFile": str(target),
            "ReplacementContent": "client.unsupported_call()",
        },
        paths=(str(target),),
    )

    result = runtime.dispatch(event, op)
    # Semantic verification never denies by default (System One balance)
    assert result.outcome == Outcome.ALLOW
    # Advisory warning injected into context
    assert any("Jev Verification Advisory" in c.text for c in result.context)

    # Encode with Antigravity adapter
    encoded = AntigravityAdapter().encode(event, result)
    assert encoded["decision"] == "allow"
    assert "additionalContext" in encoded
    assert "Verification Advisory" in encoded["additionalContext"]


def test_runtime_pre_tool_verification_advisory_codex(tmp_path: Path):
    store = Storage(tmp_path / "data/jev.sqlite3")
    settings = Settings.load(tmp_path)
    runtime = Runtime(settings, storage=store, client=MockContradictedClient())

    target = tmp_path / "service.py"
    target.write_text('"""Service module: only supports client.run()."""\n', encoding="utf-8")

    event = Event(
        kind=EventKind.TOOL_BEFORE,
        harness=Harness.CODEX,
        event_id="evt_cdx_1",
        workspace_id="ws_1",
        session_id="sess_1",
        cwd=str(tmp_path),
    )
    patch_text = (
        f"*** Update File: {target.name}\n"
        "@@ -1,1 +1,2 @@\n"
        " doc\n"
        "+client.unsupported_call()\n"
    )
    op = Operation(
        kind="file_mutation",
        tool_name="apply_patch",
        command=patch_text,
        arguments={"command": patch_text},
        paths=(str(target),),
    )

    result = runtime.dispatch(event, op)
    assert result.outcome == Outcome.ALLOW
    assert any("Jev Verification Advisory" in c.text for c in result.context)

    # Encode with Codex adapter
    encoded = CodexAdapter().encode(event, result)
    # Codex receives additionalContext in PreToolUse
    hook_output = encoded.get("hookSpecificOutput", {})
    assert hook_output.get("hookEventName") == "PreToolUse"
    assert "additionalContext" in hook_output
    assert "Verification Advisory" in hook_output["additionalContext"]


def test_shared_tool_verify_output(tmp_path: Path, monkeypatch):
    settings = Settings.load(tmp_path)
    monkeypatch.setattr(
        "jev.services.client.HttpDecisionClient.from_environment",
        lambda: MockSupportedClient(),
    )
    output = verify_output(
        settings,
        code_snippet="auth.login()",
        reference_context="auth.login() performs credential verification.",
    )
    assert output["verified"] is True
    assert output["method_supported"] >= 0.90
    assert output["support_level"] == "fully_supported"
