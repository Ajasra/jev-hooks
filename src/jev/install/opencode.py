"""Idempotent OpenCode installer: config merge, plugin ownership, manifest, backup."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from jev.install.render import opencode_config, opencode_plugin
from jev.services.paths import Settings

MANIFEST_NAME = ".jev-install.json"
MANIFEST_VERSION = 1
PLUGIN_HEADER = "// @jev-owned"
PROTECTED_KEYS = ("plugin", "provider", "agent", "permission", "model")
SCHEMA_URL = "https://opencode.ai/config.json"
CONFIG_NAMES = ("opencode.json", "opencode.jsonc")


class InstallError(RuntimeError):
    """A refusal path stopped the install or uninstall before any write."""


@dataclass(frozen=True)
class Layout:
    config_dir: Path
    explicit_config: Path | None
    plugin_file: Path
    manifest_file: Path


def global_config_dir(env: Mapping[str, str] | None = None, home: str | None = None) -> Path:
    """Mirror OpenCode itself: $(XDG_CONFIG_HOME || ~/.config)/opencode on both OSes."""
    source = os.environ if env is None else env
    xdg = source.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "opencode"
    if home is None:
        home = source.get("HOME") or source.get("USERPROFILE") or str(Path.home())
    return Path(home) / ".config" / "opencode"


def resolve_layout(
    dir_override: str = "",
    env: Mapping[str, str] | None = None,
    force_global: bool = False,
) -> Layout:
    source = os.environ if env is None else env
    if dir_override and force_global:
        raise InstallError("--dir and --global cannot be combined.")
    if dir_override:
        root = Path(dir_override).expanduser()
        explicit: Path | None = None
    else:
        root = global_config_dir(source)
        configured = source.get("OPENCODE_CONFIG")
        explicit = Path(configured).expanduser() if configured and not force_global else None
    return Layout(
        config_dir=root,
        explicit_config=explicit,
        plugin_file=root / "plugins" / "jev.ts",
        manifest_file=root / MANIFEST_NAME,
    )


def config_target(layout: Layout) -> Path:
    if layout.explicit_config is not None:
        return layout.explicit_config
    for name in CONFIG_NAMES:
        candidate = layout.config_dir / name
        if candidate.is_file():
            return candidate
    return layout.config_dir / "opencode.json"


def resolve_interpreter(env: Mapping[str, str] | None = None) -> Path:
    source = os.environ if env is None else env
    override = source.get("JEV_HOOK_PYTHON")
    if override:
        candidate = Path(override).expanduser()
        if not candidate.is_absolute():
            raise InstallError("JEV_HOOK_PYTHON must be an absolute interpreter path, never a bare name.")
        if not candidate.exists():
            raise InstallError(f"JEV_HOOK_PYTHON points at a missing interpreter: {candidate}")
        return candidate
    return Path(sys.executable)


def harness_version() -> str:
    executable = shutil.which("opencode")
    if not executable:
        return ""
    try:
        completed = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout.strip() or completed.stderr.strip()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _dump(value: dict[str, Any], original: str | None = None) -> str:
    text = json.dumps(value, indent=2, ensure_ascii=False)
    return text + "\n" if original is None or original.endswith("\n") else text


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = path.with_name(f"{path.name}.jev-{stamp}.bak")
    shutil.copy2(path, target)
    return target


def parse_config(path: Path) -> tuple[dict[str, Any] | None, bool]:
    """Return (config, existed). A parse failure aborts before any write."""
    if not path.is_file():
        return None, False
    try:
        raw = _read(path)
    except OSError as exc:
        raise InstallError(f"Cannot read {path}: {exc}") from exc
    try:
        value = json.loads(raw)
    except ValueError as exc:
        raise InstallError(
            f"{path} is not strict JSON ({exc}); refusing to touch it. "
            "Strip the comments or fix the syntax, then re-run the install."
        ) from exc
    if not isinstance(value, dict):
        raise InstallError(f"{path} must hold a JSON object, found {type(value).__name__}.")
    return value, True


@dataclass
class MergeResult:
    added: list[str] = field(default_factory=list)
    created: list[str] = field(default_factory=list)
    skills_paths: list[str] = field(default_factory=list)


def merge_owned(config: dict[str, Any], *, skills_paths: list[str], python: str) -> MergeResult:
    result = MergeResult(skills_paths=list(skills_paths))
    if "$schema" not in config:
        config["$schema"] = SCHEMA_URL
        result.added.append("$schema")
    fragment = opencode_config(python=python)
    mcp = config.get("mcp")
    if mcp is None:
        config["mcp"] = {}
        result.created.append("mcp")
    elif not isinstance(mcp, dict):
        raise InstallError("The 'mcp' block in the config is not an object; refusing to modify it.")
    config["mcp"]["jev"] = fragment["mcp"]["jev"]
    result.added.append("mcp.jev")
    for entry in skills_paths:
        skills = config.get("skills")
        if skills is None:
            skills = config["skills"] = {}
            result.created.append("skills")
        elif not isinstance(skills, dict):
            raise InstallError("The 'skills' block in the config is not an object; refusing to modify it.")
        paths = skills.get("paths")
        if paths is None:
            paths = skills["paths"] = []
            result.created.append("skills.paths")
        elif not isinstance(paths, list):
            raise InstallError("The 'skills.paths' value in the config is not a list; refusing to modify it.")
        if entry not in paths:
            paths.append(entry)
            result.added.append("skills.paths")
    return result


def plugin_state(path: Path) -> str:
    if not path.is_file():
        return "absent"
    try:
        first = _read(path).splitlines()[:1]
    except OSError:
        return "foreign"
    return "owned" if first and first[0].startswith(PLUGIN_HEADER) else "foreign"


def _load_manifest(path: Path, *, required: bool) -> dict[str, Any]:
    if not path.is_file():
        if required:
            raise InstallError(
                f"No Jev OpenCode manifest at {path}; nothing to uninstall. "
                "Hand-installed files must be removed by hand."
            )
        return {}
    try:
        value = json.loads(_read(path))
    except ValueError as exc:
        raise InstallError(f"{path} is corrupt ({exc}); repair or delete it, then retry.") from exc
    if not isinstance(value, dict):
        raise InstallError(f"{path} must hold a JSON object.")
    return value


def install(
    *,
    cwd: str | Path | None = None,
    dir_override: str = "",
    env: Mapping[str, str] | None = None,
    force_global: bool = False,
) -> dict[str, Any]:
    source = os.environ if env is None else env
    layout = resolve_layout(dir_override, source, force_global)
    previous = _load_manifest(layout.manifest_file, required=False)
    target = config_target(layout)
    config, existed = parse_config(target)
    if config is None:
        config = {}
    state = plugin_state(layout.plugin_file)
    if state == "foreign":
        raise InstallError(
            f"{layout.plugin_file} exists without the '{PLUGIN_HEADER}' header, so Jev will not overwrite it.\n"
            "Merge instruction: move that file aside (for example jev.ts.local), re-run "
            "`jev install opencode`, then re-apply your changes on top of the generated shim "
            "and keep the header as its first line."
        )
    interpreter = resolve_interpreter(source)
    version = harness_version()
    skills_paths = [str(item) for item in Settings.load(cwd).skill_roots]
    merge = merge_owned(config, skills_paths=skills_paths, python=str(interpreter))
    protected = [key for key in PROTECTED_KEYS if key in merge.added]
    if protected:
        raise InstallError(f"Refusing to own the protected config key {protected}.")
    original = _read(target) if target.is_file() else None
    rendered_config = _dump(config, original)
    rendered_plugin = opencode_plugin(python=str(interpreter), harness_version=version)

    config_changed = original != rendered_config
    plugin_text = _read(layout.plugin_file) if layout.plugin_file.is_file() else None
    plugin_changed = plugin_text != rendered_plugin

    backup_file = str(previous.get("backup_file") or "")
    if config_changed:
        if existed:
            backup_file = str(_backup(target))
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered_config, encoding="utf-8", newline="\n")
    plugin_dir_created = bool(previous.get("plugin_dir_created", False)) or not layout.plugin_file.parent.is_dir()
    if plugin_changed:
        layout.plugin_file.parent.mkdir(parents=True, exist_ok=True)
        if plugin_text is not None:
            _backup(layout.plugin_file)
        layout.plugin_file.write_text(rendered_plugin, encoding="utf-8", newline="\n")

    manifest = {
        "harness": "opencode",
        "manifest_version": MANIFEST_VERSION,
        "installed_at": previous.get("installed_at") or datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "config_dir": str(layout.config_dir),
        "config_file": str(target),
        "config_existed": bool(previous.get("config_existed", existed)),
        "plugin_file": str(layout.plugin_file),
        "plugin_dir_created": plugin_dir_created,
        "backup_file": backup_file,
        "written_sha256": {
            str(target): _sha256(rendered_config),
            str(layout.plugin_file): _sha256(rendered_plugin),
        },
        "owned_keys": merge.added,
        "created_containers": merge.created,
        "skills_paths": merge.skills_paths,
        "python": str(interpreter),
    }
    layout.manifest_file.parent.mkdir(parents=True, exist_ok=True)
    layout.manifest_file.write_text(_dump(manifest), encoding="utf-8", newline="\n")
    return {
        "config_file": str(target),
        "plugin_file": str(layout.plugin_file),
        "manifest_file": str(layout.manifest_file),
        "backup_file": backup_file,
        "config_changed": config_changed,
        "plugin_changed": plugin_changed,
        "skills_paths": merge.skills_paths,
        "python": str(interpreter),
        "harness_version": version,
    }


def _prune_config(manifest: dict[str, Any]) -> tuple[str, str]:
    raw_target = str(manifest.get("config_file") or "")
    if not raw_target:
        return "kept", "manifest records no config file"
    target = Path(raw_target)
    if not target.is_file():
        return "absent", "config file is already gone"
    original_text = _read(target)
    try:
        config = json.loads(original_text)
    except ValueError:
        return "kept", "config no longer parses; leaving the file untouched"
    if not isinstance(config, dict):
        return "kept", "config changed shape; leaving the file untouched"
    owned = list(manifest.get("owned_keys") or [])
    created = list(manifest.get("created_containers") or [])
    if "skills.paths" in owned or "skills" in created:
        skills = config.get("skills")
        if isinstance(skills, dict) and isinstance(skills.get("paths"), list):
            for entry in manifest.get("skills_paths") or []:
                while entry in skills["paths"]:
                    skills["paths"].remove(entry)
            if not skills["paths"] and ("skills.paths" in created or "skills" in created):
                skills.pop("paths", None)
            if not skills and "skills" in created:
                config.pop("skills", None)
    if "mcp.jev" in owned:
        mcp = config.get("mcp")
        if isinstance(mcp, dict):
            mcp.pop("jev", None)
            if not mcp and "mcp" in created:
                config.pop("mcp", None)
    if "$schema" in owned:
        config.pop("$schema", None)
    pruned = _dump(config, original_text)
    if not config and not manifest.get("config_existed", True):
        target.unlink()
        return "removed", "config file removed because Jev created it"
    if pruned == original_text:
        return "unchanged", "config already carries only foreign keys"
    target.write_text(pruned, encoding="utf-8", newline="\n")
    return "pruned", "removed only the Jev-owned keys"


def uninstall(
    *,
    dir_override: str = "",
    env: Mapping[str, str] | None = None,
    force_global: bool = False,
) -> dict[str, Any]:
    source = os.environ if env is None else env
    layout = resolve_layout(dir_override, source, force_global)
    manifest = _load_manifest(layout.manifest_file, required=True)
    config_action, config_detail = _prune_config(manifest)

    plugin_file = Path(str(manifest.get("plugin_file") or layout.plugin_file))
    plugin_action = "absent"
    plugin_detail = "plugin file is already gone"
    if plugin_file.is_file():
        if plugin_state(plugin_file) == "owned":
            plugin_file.unlink()
            plugin_action = "removed"
            plugin_detail = "generated shim deleted"
            parent = plugin_file.parent
            if manifest.get("plugin_dir_created") and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
        else:
            plugin_action = "kept"
            plugin_detail = "file lost its Jev header; leaving the user's shim in place"

    layout.manifest_file.unlink(missing_ok=True)
    return {
        "manifest_file": str(layout.manifest_file),
        "config_file": str(manifest.get("config_file") or ""),
        "config_action": config_action,
        "config_detail": config_detail,
        "backup_file": str(manifest.get("backup_file") or ""),
        "plugin_file": str(plugin_file),
        "plugin_action": plugin_action,
        "plugin_detail": plugin_detail,
    }
