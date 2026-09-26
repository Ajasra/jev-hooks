"""Configuration and path resolution with a trust boundary."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ALLOWED = {
    "skill_roots",
    "knowledge_roots",
    "context_budget",
    "semantic_timeout_seconds",
}
TRUSTED_ONLY = {"data_root", "rules_db", "policy_floor", "harness_identity"}


def _user_config_root() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / "Jev"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "jev"


def default_data_root() -> Path:
    override = os.environ.get("JEV_DATA_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        return (base / "Jev").resolve()
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "jev"


def find_workspace_root(start: str | Path | None = None) -> Path:
    current = Path(start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists() or (candidate / "AGENTS.md").exists():
            return candidate
    return current


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _resolve_list(values: object, base: Path) -> tuple[Path, ...]:
    if not isinstance(values, list):
        return ()
    return tuple(
        (Path(item).expanduser() if Path(item).is_absolute() else base / item).resolve()
        for item in values
        if isinstance(item, str)
    )


@dataclass(frozen=True)
class Settings:
    workspace_root: Path
    package_root: Path
    config_root: Path
    data_root: Path
    cache_root: Path
    db_path: Path
    skill_roots: tuple[Path, ...]
    knowledge_roots: tuple[Path, ...]
    context_budget: int = 12_000
    semantic_timeout_seconds: float = 0.25
    rejected_project_keys: tuple[str, ...] = ()

    @classmethod
    def load(cls, cwd: str | Path | None = None) -> "Settings":
        workspace = find_workspace_root(cwd)
        package_root = Path(__file__).resolve().parents[3]
        config_root = _user_config_root().resolve()
        user = _read_json(config_root / "config.json")
        project = _read_json(workspace / "jev.json")
        rejected = tuple(sorted(key for key in project if key in TRUSTED_ONLY))
        ordinary = dict(user)
        ordinary.update({key: value for key, value in project.items() if key in PROJECT_ALLOWED})

        data_root_value = os.environ.get("JEV_DATA_ROOT") or user.get("data_root")
        data_root = Path(data_root_value).expanduser().resolve() if data_root_value else default_data_root()
        rules_value = os.environ.get("JEV_DB_PATH") or user.get("rules_db")
        db_path = Path(rules_value).expanduser().resolve() if rules_value else data_root / "jev.sqlite3"
        skill_value: object = ordinary.get("skill_roots", [".agents/skills"])
        if os.environ.get("JEV_SKILL_ROOTS"):
            skill_value = os.environ["JEV_SKILL_ROOTS"].split(os.pathsep)
        knowledge_value: object = ordinary.get("knowledge_roots", [".agents/knowledge"])
        if os.environ.get("JEV_KNOWLEDGE_ROOTS"):
            knowledge_value = os.environ["JEV_KNOWLEDGE_ROOTS"].split(os.pathsep)
        skill_roots = _resolve_list(skill_value, workspace)
        knowledge_roots = _resolve_list(knowledge_value, workspace)
        context_budget = os.environ.get("JEV_CONTEXT_BUDGET", ordinary.get("context_budget", 12_000))
        semantic_timeout = os.environ.get(
            "JEV_SEMANTIC_TIMEOUT_SECONDS", ordinary.get("semantic_timeout_seconds", 0.25)
        )
        return cls(
            workspace_root=workspace,
            package_root=package_root,
            config_root=config_root,
            data_root=data_root,
            cache_root=data_root / "cache",
            db_path=db_path,
            skill_roots=skill_roots,
            knowledge_roots=knowledge_roots,
            context_budget=max(0, int(context_budget)),
            semantic_timeout_seconds=max(0.05, float(semantic_timeout)),
            rejected_project_keys=rejected,
        )

    def ensure_mutable_dirs(self) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)


def is_within(path: str | Path, root: str | Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except (OSError, ValueError):
        return False
