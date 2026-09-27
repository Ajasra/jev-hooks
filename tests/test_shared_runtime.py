from __future__ import annotations

import json
from pathlib import Path

import pytest

from jev.adapters.codex import CodexAdapter
from jev.cli import run_hook
from jev.contracts import Outcome
from jev.core import compaction, knowledge, skills
from jev.registry import FEATURES, TOOLS
from jev.runtime import Runtime
from jev.services.paths import Settings
from jev.services.storage import Storage, operation_digest


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


def antigravity_event(tmp_path: Path, command: str, call_id: str = "call-1") -> dict:
    return {
        "hookEventName": "PreToolUse",
        "conversationId": "same-session",
        "invocationId": call_id,
        "workspacePaths": [str(tmp_path)],
        "toolCall": {"id": call_id, "name": "run_command", "args": {"CommandLine": command}},
    }


def codex_event(tmp_path: Path, command: str, call_id: str = "call-1") -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "session_id": "same-session",
        "turn_id": "turn-1",
        "tool_use_id": call_id,
        "cwd": str(tmp_path),
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }


def test_equivalent_destructive_operation_is_denied_by_both_adapters(tmp_path: Path):
    cfg = make_settings(tmp_path)
    anti = run_hook("antigravity", antigravity_event(tmp_path, "cmd /c git reset --hard HEAD~1"), cfg)
    codex = run_hook("codex", codex_event(tmp_path, "cmd /c git reset --hard HEAD~1"), cfg)
    assert anti["decision"] == "deny"
    assert codex["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_harness_logs_are_separate_views(tmp_path: Path):
    cfg = make_settings(tmp_path)
    run_hook("antigravity", antigravity_event(tmp_path, "cmd /c git status", "anti-1"), cfg)
    run_hook("codex", codex_event(tmp_path, "cmd /c git status", "codex-1"), cfg)
    store = Storage(cfg.db_path)
    with store.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM antigravity_events").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM codex_events").fetchone()[0] == 1


def test_denial_is_replayed_for_same_invocation(tmp_path: Path):
    cfg = make_settings(tmp_path)
    raw = codex_event(tmp_path, "rm -rf build", "same-call")
    first = run_hook("codex", raw, cfg)
    second = run_hook("codex", raw, cfg)
    assert first == second
    with Storage(cfg.db_path).connect() as connection:
        row = connection.execute("SELECT status, result_json FROM invocations").fetchone()
        assert row["status"] == "complete"
        assert json.loads(row["result_json"])["outcome"] == "deny"


def test_changed_operation_cannot_reuse_old_allowance(tmp_path: Path):
    cfg = make_settings(tmp_path)
    run_hook("codex", codex_event(tmp_path, "git status", "same-call"), cfg)
    denied = run_hook("codex", codex_event(tmp_path, "git reset --hard HEAD~1", "same-call"), cfg)
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_project_config_cannot_redirect_trusted_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / ".git").mkdir()
    (tmp_path / "jev.json").write_text(
        json.dumps({"rules_db": "attacker.sqlite3", "data_root": "elsewhere", "context_budget": 42}),
        encoding="utf-8",
    )
    trusted = tmp_path / "trusted"
    monkeypatch.setenv("JEV_DATA_ROOT", str(trusted))
    cfg = Settings.load(tmp_path)
    assert cfg.db_path == trusted.resolve() / "jev.sqlite3"
    assert cfg.context_budget == 42
    assert set(cfg.rejected_project_keys) == {"data_root", "rules_db"}


def test_single_use_rule_is_harness_scoped_and_consumed_atomically(tmp_path: Path):
    cfg = make_settings(tmp_path)
    event, operation = CodexAdapter().decode(codex_event(tmp_path, "custom deploy", "deploy-1"))
    assert operation is not None
    digest = operation_digest(operation.tool_name, operation.command, operation.arguments)
    store = Storage(cfg.db_path)
    store.save_rule(
        pattern="custom deploy", tool_name="Bash", scope="single_use", harness="codex",
        workspace_id=event.workspace_id, session_id=event.session_id, digest=digest,
        decision="allow", provenance="manual_cli",
    )
    result = Runtime(cfg, storage=store, client=None).dispatch(event, operation)
    assert result.outcome == Outcome.ALLOW
    with store.connect() as connection:
        assert connection.execute("SELECT consumed_at FROM rules").fetchone()[0] is not None


def test_unknown_shell_payload_fails_closed(tmp_path: Path):
    cfg = make_settings(tmp_path)
    output = run_hook("codex", codex_event(tmp_path, ""), cfg)
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_patch_without_resolvable_target_fails_closed(tmp_path: Path):
    cfg = make_settings(tmp_path)
    raw = {
        "hook_event_name": "PreToolUse",
        "session_id": "session",
        "turn_id": "turn",
        "tool_use_id": "patch-1",
        "cwd": str(tmp_path),
        "tool_name": "apply_patch",
        "tool_input": {"command": "malformed patch"},
    }
    output = run_hook("codex", raw, cfg)
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_registry_is_shared_extension_surface():
    assert {feature.id for feature in FEATURES} >= {"safety", "skills", "knowledge", "speculative"}
    assert {tool.name for tool in TOOLS} == {
        "knowledge_search", "knowledge_learn", "skills_list", "diagnostics_status",
        "semantic_lint", "semantic_lint_feedback", "semantic_lint_stats",
    }


class SkillClient:
    def evaluate(self, state, questions, timeout):
        return {
            "skill": {"choice": "security-review", "confidence": 0.91},
            "requires_skill": {"noul": 0.94},
        }


def test_canonical_skill_source_is_shared_without_codex_double_injection(tmp_path: Path):
    skill_dir = tmp_path / ".agents/skills/security-review"
    skill_dir.mkdir(parents=True)
    body = "---\nname: security-review\ndescription: Review security boundaries.\n---\nInspect trust boundaries."
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")
    catalog = skills.load_catalog((tmp_path / ".agents/skills",))
    assert [item.name for item in catalog] == ["security-review"]
    antigravity = skills.suggest("review security", (tmp_path / ".agents/skills",), SkillClient(), 0.1)
    codex = skills.suggest(
        "review security", (tmp_path / ".agents/skills",), SkillClient(), 0.1, inject_body=False
    )
    assert antigravity.context[0].text == body
    assert codex.context == []
    assert codex.data["selected"] == "security-review"


def test_explicit_knowledge_write_and_shared_search(tmp_path: Path):
    root = tmp_path / ".agents/knowledge"
    created = knowledge.learn(
        "Authorization boundary",
        "Permission grants require verified user provenance.",
        root,
    )
    assert created["success"] is True
    found = knowledge.search("authorization boundary", (root,))
    assert found.data["selected"] == created["id"]
    assert found.context


def test_checkpoint_preserves_user_messages_and_truncates_old_tool_output():
    messages = [
        {"role": "user", "content": "Keep this exactly."},
        {"role": "assistant", "content": "", "tool_calls": [{"result": "x" * 1000}]},
        {"role": "assistant", "content": "recent-1"},
        {"role": "assistant", "content": "recent-2"},
    ]
    output = compaction.checkpoint(messages, preserve_recent=2, head_chars=20)
    assert output[0] == messages[0]
    assert output[-2:] == messages[-2:]
    assert output[1]["tool_calls"][0]["result"].startswith("x" * 20)
    assert "Checkpoint truncated" in output[1]["tool_calls"][0]["result"]
