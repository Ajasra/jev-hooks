"""Install and audit Jev's single user-scope Codex hook registration."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / ".codex" / "hooks.template.json"
HOOK_COMMAND = re.compile(r"\bjev(?:\.exe)?\s+hook\s+--harness\s+codex\b", re.IGNORECASE)
MCP_SECTION = re.compile(r"(?m)^\[mcp_servers\.jev\]\s*$")
MCP_CONFIG = '''[mcp_servers.jev]
command = "jev"
args = ["mcp", "--harness", "codex"]
startup_timeout_sec = 10
tool_timeout_sec = 30
'''


class ScopeError(RuntimeError):
    """Raised when global and project Jev registrations would overlap."""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def _contains_jev(value: Any) -> bool:
    if isinstance(value, dict):
        if any(
            isinstance(value.get(key), str) and HOOK_COMMAND.search(value[key])
            for key in ("command", "command_windows")
        ):
            return True
        return any(_contains_jev(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_jev(child) for child in value)
    return False


def _inline_jev(path: Path) -> bool:
    if not path.exists():
        return False
    return bool(HOOK_COMMAND.search(path.read_text(encoding="utf-8-sig")))


def _project_jev_sources(project_root: Path) -> list[Path]:
    codex_dir = project_root / ".codex"
    paths: list[Path] = []
    hooks_json = codex_dir / "hooks.json"
    if hooks_json.exists() and _contains_jev(_read_json(hooks_json)):
        paths.append(hooks_json)
    config_toml = codex_dir / "config.toml"
    if _inline_jev(config_toml):
        paths.append(config_toml)
    elif config_toml.exists() and MCP_SECTION.search(config_toml.read_text(encoding="utf-8-sig")):
        paths.append(config_toml)
    return paths


def _user_jev_inline_source(codex_home: Path) -> Path | None:
    config_toml = codex_home / "config.toml"
    return config_toml if _inline_jev(config_toml) else None


def _remove_jev_handlers(hooks: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for event, groups in hooks.items():
        kept_groups = []
        for group in groups if isinstance(groups, list) else []:
            if not isinstance(group, dict):
                kept_groups.append(group)
                continue
            handlers = group.get("hooks")
            if not isinstance(handlers, list):
                kept_groups.append(group)
                continue
            kept_handlers = [handler for handler in handlers if not _contains_jev(handler)]
            if kept_handlers:
                kept_groups.append({**group, "hooks": kept_handlers})
        if kept_groups:
            cleaned[event] = kept_groups
    return cleaned


def _jev_counts(hooks: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            continue
        count = 0
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                continue
            count += sum(1 for handler in group["hooks"] if _contains_jev(handler))
        counts[event] = count
    return counts


def _jev_handlers(hooks: dict[str, Any], event: str) -> list[dict[str, Any]]:
    groups = hooks.get(event)
    if not isinstance(groups, list):
        return []
    return [
        handler
        for group in groups
        if isinstance(group, dict)
        for handler in group.get("hooks", []) if isinstance(group.get("hooks"), list)
        if isinstance(handler, dict) and _contains_jev(handler)
    ]


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    if path.exists() and path.read_text(encoding="utf-8-sig") == rendered:
        return
    if path.exists():
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered)
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def _ensure_user_mcp(codex_home: Path) -> None:
    path = codex_home / "config.toml"
    existing = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    if MCP_SECTION.search(existing):
        return
    separator = "" if not existing or existing.endswith(("\n", "\r")) else "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(separator + "\n" + MCP_CONFIG)


def install_user_hooks(
    *,
    codex_home: Path,
    project_root: Path,
    template_path: Path = TEMPLATE,
) -> dict[str, int]:
    """Merge Jev's template into user hooks, preserving every unrelated handler."""
    local_sources = _project_jev_sources(project_root)
    if local_sources:
        paths = ", ".join(str(path) for path in local_sources)
        raise ScopeError(f"Project-level Jev registration found in {paths}; remove it before installing user hooks.")
    inline_source = _user_jev_inline_source(codex_home)
    if inline_source:
        raise ScopeError(
            f"Jev is already configured inline in {inline_source}; remove that registration before using hooks.json."
        )

    template = _read_json(template_path)
    template_hooks = template.get("hooks")
    if not isinstance(template_hooks, dict) or not template_hooks:
        raise ValueError(f"No lifecycle hooks found in {template_path}")

    user_path = codex_home / "hooks.json"
    user_config = _read_json(user_path)
    user_hooks = user_config.get("hooks")
    if not isinstance(user_hooks, dict):
        user_hooks = {}
    merged_hooks = _remove_jev_handlers(user_hooks)
    for event, groups in template_hooks.items():
        merged_hooks[event] = [*merged_hooks.get(event, []), *groups]
    user_config["description"] = user_config.get("description") or "Jev user-scope hooks for Codex."
    user_config["hooks"] = merged_hooks
    _ensure_user_mcp(codex_home)
    _atomic_write_json(user_path, user_config)
    return _jev_counts(merged_hooks)


def check_scope(*, codex_home: Path, project_root: Path, template_path: Path = TEMPLATE) -> list[str]:
    problems: list[str] = []
    try:
        template_hooks = _read_json(template_path).get("hooks", {})
        expected = set(template_hooks)
        global_path = codex_home / "hooks.json"
        global_hooks = _read_json(global_path).get("hooks", {})
        if not isinstance(global_hooks, dict):
            global_hooks = {}
        counts = _jev_counts(global_hooks)
        for event in sorted(expected):
            if counts.get(event, 0) != 1:
                problems.append(f"User hooks need exactly one Jev handler for {event}; found {counts.get(event, 0)}.")
            expected_handlers = _jev_handlers(template_hooks, event)
            actual_handlers = _jev_handlers(global_hooks, event)
            if len(expected_handlers) == 1 and len(actual_handlers) == 1 and actual_handlers[0] != expected_handlers[0]:
                problems.append(f"User-scope Jev handler for {event} is stale; rerun the installer.")
        for event, count in counts.items():
            if event not in expected and count:
                problems.append(f"Unexpected Jev hook event in user scope: {event} ({count}).")
        local_sources = _project_jev_sources(project_root)
        problems.extend(f"Project-scope Jev registration conflicts with user scope: {path}" for path in local_sources)
        inline_source = _user_jev_inline_source(codex_home)
        if inline_source:
            problems.append(f"User-scope Jev hooks are also defined inline in {inline_source}.")
        user_config_toml = codex_home / "config.toml"
        mcp_sections = (
            len(MCP_SECTION.findall(user_config_toml.read_text(encoding="utf-8-sig")))
            if user_config_toml.exists() else 0
        )
        if mcp_sections != 1:
            problems.append(
                f"User-scope Codex needs exactly one Jev MCP server in {user_config_toml}; found {mcp_sections}."
            )
        project_inline = project_root / ".codex" / "config.toml"
        if _inline_jev(project_inline):
            problems.append(f"Project-scope Jev hooks are also defined inline in {project_inline}.")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        problems.append(f"Could not inspect Codex hook configuration: {exc}")
    if not shutil.which("jev"):
        problems.append("The `jev` command is not on PATH for this device.")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "check"))
    parser.add_argument("--project", type=Path, default=ROOT, help="Project root to check for duplicate Jev hooks")
    parser.add_argument(
        "--codex-home",
        type=Path,
        default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")),
    )
    parser.add_argument("--template", type=Path, default=TEMPLATE)
    args = parser.parse_args(argv)
    codex_home = args.codex_home.expanduser().resolve()
    project_root = args.project.expanduser().resolve()
    try:
        if args.action == "install":
            counts = install_user_hooks(
                codex_home=codex_home,
                project_root=project_root,
                template_path=args.template.expanduser().resolve(),
            )
            print(f"Installed one user-scope Jev hook per event in {codex_home / 'hooks.json'}: {counts}")
        problems = check_scope(codex_home=codex_home, project_root=project_root, template_path=args.template)
        if problems:
            for problem in problems:
                print(f"ERROR: {problem}", file=sys.stderr)
            return 1
        if args.action == "check":
            print("Codex Jev hook scope is healthy: one user registration per event, no project duplicate.")
        return 0
    except (OSError, ValueError, ScopeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
