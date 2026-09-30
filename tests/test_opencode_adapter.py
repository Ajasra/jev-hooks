"""RFC-27 S1: OpenCode adapter contracts, boundary behavior, and CLI wiring."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jev.adapters.opencode import OpenCodeAdapter
from jev.cli import build_parser, run_hook
from jev.contracts import ContextItem, EventKind, Harness, Outcome, Result
from jev.services.paths import Settings
from jev.services.storage import Storage

FIXTURES = Path(__file__).parent / "fixtures" / "opencode"


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        workspace_root=tmp_path,
        package_root=tmp_path,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "data/cache",
        db_path=tmp_path / "data/jev.sqlite3",
        skill_roots=(tmp_path / ".agents/skills",),
        knowledge_roots=(tmp_path / ".agents/knowledge",),
        semantic_timeout_seconds=0.05,
    )


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def tool_payload(tmp_path: Path, name: str, args: dict | None, command_hint: str = "") -> dict:
    payload = {
        "hook": "tool.execute.before",
        "harness_version": "1.18.33",
        "cwd": str(tmp_path),
        "session_id": "ses_fixture",
        "turn_id": "",
        "agent": "build",
        "prompt": "",
        "native": {},
    }
    tool = {"name": name, "call_id": "call_fixture"}
    if args is not None:
        tool["args"] = args
    payload["tool"] = tool
    if command_hint:
        payload["prompt"] = command_hint
    return payload


def test_fixture_round_trips_through_decode_and_encode():
    adapter = OpenCodeAdapter()
    cases = {
        "turn.json": EventKind.TURN_BEFORE,
        "tool_before.json": EventKind.TOOL_BEFORE,
        "tool_after.json": EventKind.TOOL_AFTER,
        "checkpoint.json": EventKind.CONTEXT_CHECKPOINT,
    }
    for name, kind in cases.items():
        event, operation = adapter.decode(fixture(name))
        assert event.kind == kind
        assert event.harness == Harness.OPENCODE
        if kind in {EventKind.TURN_BEFORE, EventKind.CONTEXT_CHECKPOINT}:
            assert operation is None
        output = adapter.encode(event, Result())
        assert output["decision"] == "allow"
        assert set(output) == {"decision", "reason", "reason_code", "context", "footer", "checkpoint_context"}


def test_turn_fixture_carries_prompt_and_agent():
    event, _ = OpenCodeAdapter().decode(fixture("turn.json"))
    assert event.agent_id == "build"
    assert "SPIKE_TURN_OK" in str(event.payload["prompt"])
    assert event.turn_id.startswith("msg_")


def test_tool_fixtures_translate_to_operations():
    adapter = OpenCodeAdapter()
    before, op = adapter.decode(fixture("tool_before.json"))
    assert op is not None
    assert op.kind == "shell"
    assert op.tool_name == "bash"
    assert op.command == "echo HARMLESS_OK"
    assert before.tool_call_id.startswith("call_")
    after, op_after = adapter.decode(fixture("tool_after.json"))
    assert op_after is not None
    assert after.payload["result"]["output"].startswith("FOOTER_CHECK")


def test_checkpoint_fixture_decodes_without_operation():
    event, operation = OpenCodeAdapter().decode(fixture("checkpoint.json"))
    assert event.kind == EventKind.CONTEXT_CHECKPOINT
    assert operation is None
    assert event.session_id.startswith("ses_")


@pytest.mark.parametrize(
    ("tool_name", "args", "kind", "paths"),
    [
        ("write", {"filePath": "src/app.py", "content": "x"}, "file_mutation", ("src/app.py",)),
        ("edit", {"filePath": "src/app.py", "oldString": "a", "newString": "b"}, "file_mutation", ("src/app.py",)),
        ("apply_patch", {"patchText": "*** Begin Patch\n*** Add File: new.py\n+line\n*** End Patch"},
         "file_mutation", ("new.py",)),
        ("bash", {"command": "git status"}, "shell", ()),
        ("task", {"prompt": "explore"}, "tool", ()),
        ("jev_semantic_lint", {"staged": True}, "tool", ()),
    ],
)
def test_tool_translation_table(tool_name: str, args: dict, kind: str, paths: tuple):
    payload = {
        "hook": "tool.execute.before",
        "cwd": "/abs/project",
        "session_id": "ses_fixture",
        "tool": {"name": tool_name, "call_id": "call_fixture", "args": args},
        "native": {},
    }
    _, operation = OpenCodeAdapter().decode(payload)
    assert operation is not None
    assert operation.kind == kind
    assert operation.paths == paths


def test_shell_dialect_taken_from_args():
    payload = {
        "hook": "tool.execute.before",
        "cwd": "/abs/project",
        "session_id": "ses_fixture",
        "tool": {"name": "bash", "call_id": "c", "args": {"command": "dir", "shell": "cmd"}},
        "native": {},
    }
    _, operation = OpenCodeAdapter().decode(payload)
    assert operation is not None
    assert operation.shell == "cmd"


def test_unknown_hook_is_rejected():
    with pytest.raises(ValueError, match="Unsupported OpenCode hook"):
        OpenCodeAdapter().decode({"hook": "permission.ask", "cwd": "/abs/project"})


def test_encode_maps_outcomes_to_decisions():
    adapter = OpenCodeAdapter()
    event, _ = adapter.decode(fixture("tool_before.json"))
    assert adapter.encode(event, Result(outcome=Outcome.DENY, reason="blocked", reason_code="recursive_delete"))["decision"] == "deny"
    assert adapter.encode(event, Result(outcome=Outcome.NEEDS_CONFIRMATION, reason="confirm"))["decision"] == "ask"
    assert adapter.encode(event, Result(outcome=Outcome.ALLOW))["decision"] == "allow"


def test_turn_encode_injects_context_with_telemetry():
    adapter = OpenCodeAdapter()
    event, _ = adapter.decode(fixture("turn.json"))
    result = Result(context=[ContextItem("speculative", "dirty paths: build/")], duration_ms=12.5)
    output = adapter.encode(event, result)
    assert "dirty paths: build/" in output["context"]
    assert "<!-- jev-telemetry: 1 item(s) injected | outcome: abstain | latency: 12.5ms -->" in output["context"]


def test_tool_after_encode_emits_footer():
    adapter = OpenCodeAdapter()
    event, _ = adapter.decode(fixture("tool_after.json"))
    assert "<!-- jev-telemetry" in adapter.encode(event, Result())["footer"]
    result = Result(context=[ContextItem("knowledge_proposer", "consider recording")])
    assert adapter.encode(event, result)["footer"].startswith("consider recording")


def test_checkpoint_encode_pushes_context_list():
    adapter = OpenCodeAdapter()
    event, _ = adapter.decode(fixture("checkpoint.json"))
    output = adapter.encode(event, Result(context=[ContextItem("compaction", "summary seed")]))
    assert output["checkpoint_context"] == ["summary seed"]


def test_malformed_shell_fails_closed(tmp_path: Path):
    cfg = make_settings(tmp_path)
    output = run_hook("opencode", tool_payload(tmp_path, "bash", {}), cfg)
    assert output["decision"] == "deny"
    assert output["reason_code"] == "malformed_tool_event"


def test_missing_tool_fails_closed(tmp_path: Path):
    cfg = make_settings(tmp_path)
    payload = {"hook": "tool.execute.before", "cwd": str(tmp_path), "session_id": "s", "native": {}}
    output = run_hook("opencode", payload, cfg)
    assert output["decision"] == "deny"


def test_malformed_file_mutation_fails_open(tmp_path: Path):
    cfg = make_settings(tmp_path)
    output = run_hook("opencode", tool_payload(tmp_path, "write", {}), cfg)
    assert output["decision"] == "allow"
    assert output["reason"].startswith("Fail-open on inspection error")


def test_malformed_tool_after_fails_open(tmp_path: Path):
    cfg = make_settings(tmp_path)
    payload = {"hook": "tool.execute.after", "cwd": str(tmp_path), "session_id": "s", "native": {}}
    assert run_hook("opencode", payload, cfg) == {}


def test_codex_apply_patch_decode_error_still_fails_closed(tmp_path: Path):
    # RFC-27 non-interference: Codex's own apply_patch tool must keep failing closed on
    # malformed input even though OpenCode file mutations fail open in the same boundary.
    cfg = make_settings(tmp_path)
    raw = {
        "hook_event_name": "PreToolUse",
        "session_id": "s",
        "turn_id": "t",
        "tool_use_id": "c1",
        "cwd": str(tmp_path),
        "tool_name": "apply_patch",
        "tool_input": "not-an-object",
    }
    output = run_hook("codex", raw, cfg)
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_routine_command_is_allowed_and_denial_replays(tmp_path: Path):
    cfg = make_settings(tmp_path)
    raw = tool_payload(tmp_path, "bash", {"command": "echo HARMLESS_OK"})
    assert run_hook("opencode", raw, cfg)["decision"] == "allow"
    denied = tool_payload(tmp_path, "bash", {"command": "rm -rf build"})
    first = run_hook("opencode", denied, cfg)
    second = run_hook("opencode", denied, cfg)
    assert first["decision"] == "deny"
    assert first == second


def test_turn_hook_dispatches_end_to_end(tmp_path: Path):
    cfg = make_settings(tmp_path)
    raw = fixture("turn.json")
    raw["cwd"] = str(tmp_path)
    output = run_hook("opencode", raw, cfg)
    assert output["decision"] == "allow"
    assert isinstance(output["context"], str)


def test_opencode_events_view_records_rows(tmp_path: Path):
    cfg = make_settings(tmp_path)
    run_hook("opencode", tool_payload(tmp_path, "bash", {"command": "echo HARMLESS_OK"}), cfg)
    with Storage(cfg.db_path).connect() as connection:
        count = connection.execute("SELECT COUNT(*) FROM opencode_events").fetchone()[0]
    assert count >= 1


@pytest.mark.parametrize(
    "argv",
    [
        ["hook", "--harness", "opencode"],
        ["stats", "--harness", "opencode"],
        ["mcp", "--harness", "opencode"],
        ["lint", "--harness", "opencode"],
        ["authorize", "--harness", "opencode", "--tool", "bash", "--command", "echo x",
         "--workspace-id", "ws"],
    ],
)
def test_cli_accepts_opencode_on_every_harness_path(argv: list[str]):
    args = build_parser().parse_args(argv)
    assert args.harness == "opencode"


def test_harness_enum_exposes_opencode():
    assert Harness.OPENCODE.value == "opencode"
