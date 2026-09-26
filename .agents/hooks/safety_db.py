#!/usr/bin/env python3
"""Compatibility CLI for the shared harness-aware Jev database."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from jev.core.safety import CRITICAL_PATTERNS, FILE_TOOLS as SKIP_CRITICAL_TOOLS, clean_command, critical_reason
from jev.services.paths import Settings
from jev.services.storage import Storage, operation_digest

DEFAULT_DB_PATH = Settings.load(ROOT).db_path


def get_db_path() -> Path:
    return Settings.load(ROOT).db_path


def _storage(db_path: Path | None = None) -> Storage:
    return Storage(db_path or get_db_path())


def init_db(db_path: Path | None = None) -> None:
    _storage(db_path).initialize()


def is_critical(tool_name: str, command: str) -> tuple[bool, str]:
    if tool_name in SKIP_CRITICAL_TOOLS:
        return False, ""
    reason = critical_reason(command)
    return bool(reason), reason


def clean_command_string(command: str) -> str:
    return clean_command(command)


def save_decision(
    pattern: str,
    tool_name: str = "*",
    scope: str = "always",
    decision: str = "allow",
    conversation_id: str | None = None,
    workspace_path: str | None = None,
    reason: str = "",
    harness: str = "antigravity",
    db_path: Path | None = None,
) -> bool:
    critical, critical_code = is_critical(tool_name, pattern)
    if critical and decision == "allow":
        raise ValueError(f"Cannot allow invariant operation: {critical_code}")
    _storage(db_path).save_rule(
        pattern=clean_command(pattern), tool_name=tool_name, scope=scope,
        harness=harness, workspace_id=workspace_path or "", session_id=conversation_id or "",
        digest=operation_digest(tool_name, pattern, {"command": pattern}) if scope == "single_use" else "",
        decision=decision, provenance="manual_cli", reason=reason,
    )
    return True


def check_decision(
    tool_name: str,
    command: str,
    conversation_id: str = "",
    workspace_path: str = "",
    harness: str = "antigravity",
    db_path: Path | None = None,
) -> tuple[str, str]:
    critical, reason = is_critical(tool_name, command)
    if critical:
        return "deny", f"Critical destructive operation: {reason}"
    decision, why, _ = _storage(db_path).find_rule(
        harness=harness, workspace_id=workspace_path, session_id=conversation_id,
        tool_name=tool_name, command=clean_command(command),
        digest=operation_digest(tool_name, command, {"command": command}),
    )
    return decision, why


def clear_all_rules(db_path: Path | None = None) -> int:
    store = _storage(db_path)
    store.initialize()
    with store.connect() as connection:
        return connection.execute("DELETE FROM rules").rowcount


def clear_logs(db_path: Path | None = None) -> tuple[int, int]:
    store = _storage(db_path)
    store.initialize()
    with store.connect() as connection:
        count = connection.execute("DELETE FROM events").rowcount
    return count, 0


def log_decision(*args: Any, **kwargs: Any) -> None:
    return None


def log_speculative_decision(*args: Any, **kwargs: Any) -> int:
    return -1


def record_speculative_feedback(*args: Any, **kwargs: Any) -> None:
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Jev shared policy database")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--review", action="store_true")
    parser.add_argument("--clear-all", action="store_true")
    parser.add_argument("--clear-logs", action="store_true")
    parser.add_argument("--test-cmd")
    parser.add_argument("--tool", default="run_command")
    parser.add_argument("--harness", choices=("antigravity", "codex"), default="antigravity")
    args = parser.parse_args()
    store = _storage()
    if args.clear_all:
        print(clear_all_rules())
        return 0
    if args.clear_logs:
        print(clear_logs()[0])
        return 0
    if args.test_cmd:
        critical, reason = is_critical(args.tool, args.test_cmd)
        decision, rule_reason = check_decision(args.tool, args.test_cmd, harness=args.harness)
        print(f"Critical: {critical} {reason}")
        print(f"Decision: {decision} {rule_reason}")
        return 0
    rows = store.events(args.harness if args.review else None)
    for row in rows:
        print(f"{row['created_at']} {row['harness']} {row['feature']} {row['outcome']} {row['reason_code']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
