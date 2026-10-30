from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import codex_hooks


ROOT = Path(__file__).resolve().parent.parent


def test_repo_template_has_one_portable_global_registration_per_event():
    template = json.loads((ROOT / ".codex/hooks.template.json").read_text(encoding="utf-8"))
    project_hooks = json.loads((ROOT / ".codex/hooks.json").read_text(encoding="utf-8"))
    project_config = (ROOT / ".codex/config.toml").read_text(encoding="utf-8")

    assert set(template["hooks"]) == {"SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse"}
    assert project_hooks["hooks"] == {}
    assert "[mcp_servers.jev]" not in project_config
    for groups in template["hooks"].values():
        handlers = [handler for group in groups for handler in group["hooks"] if codex_hooks._contains_jev(handler)]
        assert len(handlers) == 1
        assert handlers[0]["command"] == "jev hook --harness codex"
        assert handlers[0]["command_windows"] == "jev hook --harness codex"


def test_installer_replaces_jev_groups_and_preserves_other_global_handlers(tmp_path):
    codex_home = tmp_path / "user" / ".codex"
    project = tmp_path / "project"
    old_global = {
        "description": "User hooks",
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "jev hook --harness codex"}]},
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "user-policy"}]},
            ],
            "Stop": [{"hooks": [{"type": "command", "command": "user-stop"}]}],
        },
    }
    codex_home.mkdir(parents=True)
    (codex_home / "hooks.json").write_text(json.dumps(old_global), encoding="utf-8")

    counts = codex_hooks.install_user_hooks(codex_home=codex_home, project_root=project)
    installed = json.loads((codex_home / "hooks.json").read_text(encoding="utf-8"))
    pretool_handlers = [
        handler
        for group in installed["hooks"]["PreToolUse"]
        for handler in group["hooks"]
    ]

    assert counts["PreToolUse"] == 1
    assert sum(codex_hooks._contains_jev(handler) for handler in pretool_handlers) == 1
    assert any(handler.get("command") == "user-policy" for handler in pretool_handlers)
    assert installed["hooks"]["Stop"] == old_global["hooks"]["Stop"]
    assert (codex_home / "hooks.json.bak").exists()
    assert "[mcp_servers.jev]" in (codex_home / "config.toml").read_text(encoding="utf-8")


def test_installer_refuses_project_jev_hook_instead_of_creating_double_dispatch(tmp_path):
    project = tmp_path / "project"
    local_codex = project / ".codex"
    local_codex.mkdir(parents=True)
    (local_codex / "hooks.json").write_text(
        json.dumps({"hooks": {"PreToolUse": [{"hooks": [{"command": "jev hook --harness codex"}]}]}}),
        encoding="utf-8",
    )

    with pytest.raises(codex_hooks.ScopeError, match="Project-level Jev registration"):
        codex_hooks.install_user_hooks(codex_home=tmp_path / "user", project_root=project)


def test_scope_check_requires_one_global_registration_and_no_project_duplicate(tmp_path, monkeypatch):
    codex_home = tmp_path / "user"
    project = tmp_path / "project"
    codex_home.mkdir()
    codex_hooks.install_user_hooks(codex_home=codex_home, project_root=project)
    monkeypatch.setattr(codex_hooks.shutil, "which", lambda name: "jev.exe" if name == "jev" else None)

    assert codex_hooks.check_scope(codex_home=codex_home, project_root=project) == []

    (project / ".codex").mkdir(parents=True)
    (project / ".codex" / "config.toml").write_text(
        '[mcp_servers.jev]\ncommand = "jev"\n', encoding="utf-8"
    )
    problems = codex_hooks.check_scope(codex_home=codex_home, project_root=project)
    assert any("Project-scope Jev registration conflicts" in problem for problem in problems)


def test_scope_check_detects_stale_global_template_after_repo_update(tmp_path, monkeypatch):
    codex_home = tmp_path / "user"
    project = tmp_path / "project"
    codex_home.mkdir()
    codex_hooks.install_user_hooks(codex_home=codex_home, project_root=project)
    monkeypatch.setattr(codex_hooks.shutil, "which", lambda name: "jev.exe" if name == "jev" else None)
    hooks_path = codex_home / "hooks.json"
    hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
    hooks["hooks"]["PreToolUse"][0]["hooks"][0]["command"] = r"C:\old-device\jev.exe hook --harness codex"
    hooks_path.write_text(json.dumps(hooks), encoding="utf-8")

    problems = codex_hooks.check_scope(codex_home=codex_home, project_root=project)
    assert any("PreToolUse is stale" in problem for problem in problems)
