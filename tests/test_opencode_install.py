"""RFC-27 S3: OpenCode installer ownership, refusal paths, and byte-stable uninstall."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jev.install.opencode import (
    InstallError,
    config_target,
    global_config_dir,
    install,
    merge_owned,
    plugin_state,
    resolve_layout,
    resolve_interpreter,
    uninstall,
)

ORIGINAL = json.dumps(
    {
        "plugin": ["@cortexkit/opencode-magic-context@latest"],
        "provider": {},
        "model": "anthropic/claude-sonnet-4-5",
        "agent": {"build": {"tools": {"write": True}}},
        "permission": {"edit": "allow"},
    },
    indent=2,
) + "\n"


def home_env(tmp_path: Path) -> dict[str, str]:
    return {"HOME": str(tmp_path)}


def root(tmp_path: Path) -> Path:
    return tmp_path / ".config" / "opencode"


def test_install_adds_only_owned_keys(tmp_path: Path):
    config = root(tmp_path) / "opencode.json"
    config.parent.mkdir(parents=True)
    config.write_text(ORIGINAL, encoding="utf-8")
    report = install(env=home_env(tmp_path), cwd=tmp_path)

    data = json.loads(config.read_text(encoding="utf-8"))
    assert data["plugin"] == ["@cortexkit/opencode-magic-context@latest"]
    assert data["provider"] == {}
    assert data["model"] == "anthropic/claude-sonnet-4-5"
    assert data["agent"] == {"build": {"tools": {"write": True}}}
    assert data["permission"] == {"edit": "allow"}
    assert data["$schema"] == "https://opencode.ai/config.json"
    command = data["mcp"]["jev"]["command"]
    assert command[:4] == [report["python"], "-m", "jev", "mcp"]
    assert command[-2:] == ["--harness", "opencode"]
    assert data["mcp"]["jev"]["enabled"] is True
    assert data["skills"]["paths"] == [str(tmp_path / ".agents" / "skills")]
    assert report["backup_file"] and Path(report["backup_file"]).is_file()


def test_install_writes_owned_plugin_and_manifest(tmp_path: Path):
    config = root(tmp_path) / "opencode.json"
    config.parent.mkdir(parents=True)
    config.write_text(ORIGINAL, encoding="utf-8")
    report = install(env=home_env(tmp_path), cwd=tmp_path)
    plugin = Path(report["plugin_file"])
    assert plugin == root(tmp_path) / "plugins" / "jev.ts"
    assert plugin.read_text(encoding="utf-8").splitlines()[0].startswith("// @jev-owned")
    assert plugin_state(plugin) == "owned"
    manifest = json.loads(Path(report["manifest_file"]).read_text(encoding="utf-8"))
    assert manifest["harness"] == "opencode"
    assert manifest["owned_keys"] == ["$schema", "mcp.jev", "skills.paths"]
    assert manifest["created_containers"] == ["mcp", "skills", "skills.paths"]
    assert manifest["config_existed"] is True
    assert set(manifest["written_sha256"]) == {report["config_file"], report["plugin_file"]}


def test_install_is_idempotent(tmp_path: Path):
    config = root(tmp_path) / "opencode.json"
    config.parent.mkdir(parents=True)
    config.write_text(ORIGINAL, encoding="utf-8")
    first = install(env=home_env(tmp_path), cwd=tmp_path)
    second = install(env=home_env(tmp_path), cwd=tmp_path)
    assert first["config_changed"] is True
    assert second["config_changed"] is False
    assert second["plugin_changed"] is False
    assert len(list(root(tmp_path).glob("opencode.json.jev-*.bak"))) == 1
    assert second["manifest_file"] == first["manifest_file"]


def test_install_refuses_comment_bearing_config(tmp_path: Path):
    config = root(tmp_path) / "opencode.json"
    config.parent.mkdir(parents=True)
    text = '{\n  // hand written\n  "plugin": []\n}\n'
    config.write_text(text, encoding="utf-8")
    with pytest.raises(InstallError, match="not strict JSON"):
        install(env=home_env(tmp_path), cwd=tmp_path)
    assert config.read_text(encoding="utf-8") == text
    assert not (root(tmp_path) / "plugins" / "jev.ts").exists()
    assert not (root(tmp_path) / ".jev-install.json").exists()


def test_install_refuses_unmarked_plugin_file(tmp_path: Path):
    plugin = root(tmp_path) / "plugins" / "jev.ts"
    plugin.parent.mkdir(parents=True)
    text = "// hand written shim\nexport default {}\n"
    plugin.write_text(text, encoding="utf-8")
    with pytest.raises(InstallError, match="Merge instruction"):
        install(env=home_env(tmp_path), cwd=tmp_path)
    assert plugin.read_text(encoding="utf-8") == text
    assert not (root(tmp_path) / "opencode.json").exists()
    assert not (root(tmp_path) / ".jev-install.json").exists()


def test_uninstall_restores_config_byte_for_byte(tmp_path: Path):
    config = root(tmp_path) / "opencode.json"
    config.parent.mkdir(parents=True)
    config.write_text(ORIGINAL, encoding="utf-8")
    before = config.read_bytes()
    report = install(env=home_env(tmp_path), cwd=tmp_path)
    out = uninstall(env=home_env(tmp_path))
    assert out["config_action"] == "pruned"
    assert out["plugin_action"] == "removed"
    assert config.read_bytes() == before
    assert not Path(out["plugin_file"]).exists()
    assert not Path(out["manifest_file"]).exists()
    assert report["backup_file"] and Path(report["backup_file"]).is_file()
    assert not (root(tmp_path) / "plugins").exists()


def test_uninstall_keeps_keys_the_user_added_after_install(tmp_path: Path):
    config = root(tmp_path) / "opencode.json"
    config.parent.mkdir(parents=True)
    config.write_text(ORIGINAL, encoding="utf-8")
    install(env=home_env(tmp_path), cwd=tmp_path)
    data = json.loads(config.read_text(encoding="utf-8"))
    data["model"] = "openrouter/auto"
    config.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    uninstall(env=home_env(tmp_path))
    after = json.loads(config.read_text(encoding="utf-8"))
    assert after["model"] == "openrouter/auto"
    assert after["plugin"] == ["@cortexkit/opencode-magic-context@latest"]
    assert "mcp" not in after
    assert "skills" not in after
    assert "$schema" not in after


def test_uninstall_removes_a_config_jev_created(tmp_path: Path):
    install(env=home_env(tmp_path), cwd=tmp_path)
    uninstall(env=home_env(tmp_path))
    assert not (root(tmp_path) / "opencode.json").exists()
    assert not (root(tmp_path) / ".jev-install.json").exists()


def test_uninstall_without_manifest_fails_cleanly(tmp_path: Path):
    with pytest.raises(InstallError, match="nothing to uninstall"):
        uninstall(env=home_env(tmp_path))


def test_dir_flag_targets_another_directory(tmp_path: Path):
    target = tmp_path / "alt"
    report = install(env=home_env(tmp_path), dir_override=str(target), cwd=tmp_path)
    assert report["config_file"] == str(target / "opencode.json")
    assert report["plugin_file"] == str(target / "plugins" / "jev.ts")
    assert (target / "opencode.json").is_file()
    out = uninstall(env=home_env(tmp_path), dir_override=str(target))
    assert out["config_action"] == "removed"
    assert not (target / "opencode.json").exists()


def test_dir_and_global_conflict(tmp_path: Path):
    with pytest.raises(InstallError, match="cannot be combined"):
        install(dir_override=str(tmp_path), force_global=True, env=home_env(tmp_path), cwd=tmp_path)


def test_global_config_dir_rule_matches_opencode_on_both_boots():
    assert global_config_dir({"XDG_CONFIG_HOME": "/home/u/.config"}, None) == Path("/home/u/.config/opencode")
    assert global_config_dir({"HOME": "/home/u"}, None) == Path("/home/u/.config/opencode")
    windows = global_config_dir({"USERPROFILE": r"C:\Users\vasily"}, None)
    assert windows == Path(r"C:\Users\vasily") / ".config" / "opencode"
    assert "AppData" not in str(
        global_config_dir({"APPDATA": r"C:\Users\vasily\AppData\Roaming", "USERPROFILE": r"C:\Users\vasily"}, None)
    )


def test_open_code_config_env_points_at_the_file(tmp_path: Path):
    explicit = tmp_path / "custom.json"
    layout = resolve_layout(env={"OPENCODE_CONFIG": str(explicit), "HOME": str(tmp_path)})
    assert config_target(layout) == explicit
    assert layout.plugin_file == root(tmp_path) / "plugins" / "jev.ts"


def test_windows_paths_render_as_pure_string_fixtures():
    config: dict[str, object] = {}
    merge_owned(
        config,
        skills_paths=[r"C:\repo\.agents\skills"],
        python=r"C:\repo\.venv\Scripts\python.exe",
    )
    command = config["mcp"]["jev"]["command"]  # type: ignore[index]
    assert command[:4] == [r"C:\repo\.venv\Scripts\python.exe", "-m", "jev", "mcp"]
    assert command[-2:] == ["--harness", "opencode"]
    assert config["skills"]["paths"] == [r"C:\repo\.agents\skills"]  # type: ignore[index]
    round_trip = json.loads(json.dumps(config))
    assert round_trip["mcp"]["jev"]["command"][0] == r"C:\repo\.venv\Scripts\python.exe"


def test_hook_python_override_must_exist(tmp_path: Path):
    missing = tmp_path / "python.exe"
    with pytest.raises(InstallError, match="missing interpreter"):
        resolve_interpreter({"JEV_HOOK_PYTHON": str(missing)})
    with pytest.raises(InstallError, match="absolute interpreter path"):
        resolve_interpreter({"JEV_HOOK_PYTHON": "python3"})
    assert resolve_interpreter({}) == Path(__import__("sys").executable)


def test_protected_keys_are_never_owned():
    config: dict[str, object] = {"plugin": ["keep"], "provider": {}, "model": "m", "agent": {}, "permission": {}}
    merge_owned(config, skills_paths=["/s"], python="/p")
    assert config["plugin"] == ["keep"]
    assert config["provider"] == {}
    assert config["model"] == "m"
    assert config["agent"] == {}
    assert config["permission"] == {}
    assert "mcp.jev" in merge_owned(dict(config), skills_paths=[], python="/p").added
