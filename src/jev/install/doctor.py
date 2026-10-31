"""Read-only compatibility diagnostics."""

from __future__ import annotations

import json
import sqlite3
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from jev.install.render import capability_manifest
from jev.core.skills import load_catalog
from jev.core.knowledge import load_items
from jev.services.paths import Settings


def opencode_report(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    from jev.install.opencode import (
        InstallError,
        config_target,
        harness_version,
        plugin_state,
        resolve_interpreter,
        resolve_layout,
    )

    layout = resolve_layout(env=env)
    target = config_target(layout)
    section: dict[str, Any] = {
        "config_dir": str(layout.config_dir),
        "config_file": str(target),
        "manifest_file": str(layout.manifest_file),
        "installed": layout.manifest_file.is_file(),
        "plugin_file": str(layout.plugin_file),
        "plugin_state": plugin_state(layout.plugin_file),
        "interpreter": "",
        "interpreter_error": "",
        "opencode_version": harness_version(),
        "skills_paths": [],
        "mcp": {"present": False, "enabled": False, "command": [], "matches_interpreter": False},
        "config_error": "",
    }
    try:
        section["interpreter"] = str(resolve_interpreter(env))
    except InstallError as exc:
        section["interpreter_error"] = str(exc)
    if target.is_file():
        try:
            parsed = json.loads(target.read_text(encoding="utf-8"))
        except ValueError as exc:
            section["config_error"] = str(exc)
            return section
        if not isinstance(parsed, dict):
            section["config_error"] = "config root is not a JSON object"
            return section
        skills = parsed.get("skills")
        paths = skills.get("paths") if isinstance(skills, dict) else None
        if isinstance(paths, list):
            section["skills_paths"] = [str(item) for item in paths]
        mcp = parsed.get("mcp")
        entry = mcp.get("jev") if isinstance(mcp, dict) else None
        if isinstance(entry, dict):
            command = entry.get("command")
            command = [str(item) for item in command] if isinstance(command, list) else []
            section["mcp"] = {
                "present": True,
                "enabled": bool(entry.get("enabled", True)),
                "command": command,
                "matches_interpreter": bool(command) and command[0] == section["interpreter"],
            }
    return section


def registration_problems(section: dict[str, Any]) -> list[str]:
    """Registrations a fresh install must keep present; empty means healthy."""
    if not section.get("installed"):
        return []
    problems: list[str] = []
    if section["config_error"]:
        problems.append(f"config no longer parses: {section['config_error']}")
    if section["plugin_state"] != "owned":
        problems.append(f"plugin file is {section['plugin_state']}, expected an owned '// @jev-owned' shim")
    if not section["mcp"]["present"]:
        problems.append("mcp.jev server block is missing")
    elif not section["mcp"]["enabled"]:
        problems.append("mcp.jev server block is disabled")
    elif not section["mcp"]["matches_interpreter"]:
        problems.append("mcp.jev command does not start with the resolved interpreter")
    skills = section["skills_paths"]
    if not skills:
        problems.append("skills.paths entry is missing")
    if section["interpreter_error"]:
        problems.append(section["interpreter_error"])
    elif section["interpreter"] and not _interpreter_exists(section["interpreter"]):
        problems.append(f"interpreter is missing on disk: {section['interpreter']}")
    return problems


def _interpreter_exists(interpreter: str) -> bool:
    return Path(interpreter).exists()


def report(settings: Settings) -> dict[str, Any]:
    section = opencode_report()
    return {
        "python": sys.version.split()[0],
        "sqlite": sqlite3.sqlite_version,
        "workspace_root": str(settings.workspace_root),
        "package_root": str(settings.package_root),
        "data_root": str(settings.data_root),
        "db_path": str(settings.db_path),
        "skill_roots": [str(path) for path in settings.skill_roots],
        "knowledge_roots": [str(path) for path in settings.knowledge_roots],
        "skill_count": len(load_catalog(settings.skill_roots)),
        "knowledge_count": len(load_items(settings.knowledge_roots)),
        "missing_skill_roots": [str(path) for path in settings.skill_roots if not path.is_dir()],
        "missing_knowledge_roots": [str(path) for path in settings.knowledge_roots if not path.is_dir()],
        "semantic_timeout_seconds": settings.semantic_timeout_seconds,
        "lint_rule_roots": [str(path) for path in settings.lint_rule_roots],
        "harness_identity": settings.harness_identity,
        "rejected_project_keys": list(settings.rejected_project_keys),
        "capabilities": capability_manifest(),
        "opencode": section,
        "problems": registration_problems(section),
    }


def format_report(settings: Settings) -> str:
    return json.dumps(report(settings), indent=2, sort_keys=True)
