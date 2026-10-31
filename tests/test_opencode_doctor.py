"""RFC-27 S4: doctor reports the OpenCode registration and fails loudly when one is missing."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jev.install.doctor import opencode_report, registration_problems
from jev.install.opencode import install


def home_env(tmp_path: Path) -> dict[str, str]:
    return {"HOME": str(tmp_path)}


def root(tmp_path: Path) -> Path:
    return tmp_path / ".config" / "opencode"


def test_fresh_install_reports_every_registration(tmp_path: Path):
    install(env=home_env(tmp_path), cwd=tmp_path)
    section = opencode_report(env=home_env(tmp_path))
    assert section["installed"] is True
    assert section["config_dir"] == str(root(tmp_path))
    assert section["config_file"] == str(root(tmp_path) / "opencode.json")
    assert section["plugin_state"] == "owned"
    from jev.services.paths import Settings

    assert section["skills_paths"] == [str(path) for path in Settings.load(tmp_path).skill_roots]
    assert section["mcp"] == {
        "present": True,
        "enabled": True,
        "command": [str(sys.executable), "-m", "jev", "mcp", "--cwd", ".", "--harness", "opencode"],
        "matches_interpreter": True,
    }
    assert section["interpreter"] == str(sys.executable)
    assert section["config_error"] == ""
    assert isinstance(section["opencode_version"], str)
    assert registration_problems(section) == []


def test_uninstalled_machine_reports_nothing_missing(tmp_path: Path):
    section = opencode_report(env=home_env(tmp_path))
    assert section["installed"] is False
    assert section["plugin_state"] == "absent"
    assert registration_problems(section) == []


def test_missing_mcp_block_is_a_registered_failure(tmp_path: Path):
    install(env=home_env(tmp_path), cwd=tmp_path)
    config = root(tmp_path) / "opencode.json"
    data = json.loads(config.read_text(encoding="utf-8"))
    del data["mcp"]
    config.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    problems = registration_problems(opencode_report(env=home_env(tmp_path)))
    assert any("mcp.jev" in item for item in problems)


def test_deleted_plugin_is_a_registered_failure(tmp_path: Path):
    install(env=home_env(tmp_path), cwd=tmp_path)
    (root(tmp_path) / "plugins" / "jev.ts").unlink()
    problems = registration_problems(opencode_report(env=home_env(tmp_path)))
    assert any("plugin" in item for item in problems)


def test_comment_bearing_config_is_reported_not_raised(tmp_path: Path):
    install(env=home_env(tmp_path), cwd=tmp_path)
    config = root(tmp_path) / "opencode.json"
    config.write_text('{\n  // hand written\n  "mcp": {}\n}\n', encoding="utf-8")
    section = opencode_report(env=home_env(tmp_path))
    assert section["config_error"]
    problems = registration_problems(section)
    assert any("parses" in item for item in problems)


def test_missing_skills_entry_is_a_registered_failure(tmp_path: Path):
    install(env=home_env(tmp_path), cwd=tmp_path)
    config = root(tmp_path) / "opencode.json"
    data = json.loads(config.read_text(encoding="utf-8"))
    del data["skills"]
    config.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    problems = registration_problems(opencode_report(env=home_env(tmp_path)))
    assert any("skills.paths" in item for item in problems)


def test_broken_interpreter_override_is_reported(tmp_path: Path):
    install(env=home_env(tmp_path), cwd=tmp_path)
    env = dict(home_env(tmp_path), JEV_HOOK_PYTHON=str(tmp_path / "gone" / "python"))
    section = opencode_report(env=env)
    assert section["interpreter_error"]
    problems = registration_problems(section)
    assert any("missing interpreter" in item for item in problems)
