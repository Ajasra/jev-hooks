"""Read-only compatibility diagnostics."""

from __future__ import annotations

import json
import sqlite3
import sys
from typing import Any

from jev.install.render import capability_manifest
from jev.services.paths import Settings


def report(settings: Settings) -> dict[str, Any]:
    return {
        "python": sys.version.split()[0],
        "sqlite": sqlite3.sqlite_version,
        "workspace_root": str(settings.workspace_root),
        "package_root": str(settings.package_root),
        "data_root": str(settings.data_root),
        "db_path": str(settings.db_path),
        "skill_roots": [str(path) for path in settings.skill_roots],
        "knowledge_roots": [str(path) for path in settings.knowledge_roots],
        "lint_rule_roots": [str(path) for path in settings.lint_rule_roots],
        "harness_identity": settings.harness_identity,
        "rejected_project_keys": list(settings.rejected_project_keys),
        "capabilities": capability_manifest(),
    }


def format_report(settings: Settings) -> str:
    return json.dumps(report(settings), indent=2, sort_keys=True)
