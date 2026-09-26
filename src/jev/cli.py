"""Command-line and hook entry point for the shared runtime."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from jev.adapters import AntigravityAdapter, CodexAdapter
from jev.contracts import EventKind, Outcome
from jev.core import safety
from jev.install.doctor import format_report
from jev.runtime import Runtime
from jev.services.paths import Settings
from jev.services.storage import Storage, operation_digest


def _adapter(name: str):
    if name == "antigravity":
        return AntigravityAdapter()
    if name == "codex":
        return CodexAdapter()
    raise ValueError(f"Unknown harness: {name}")


def run_hook(harness: str, raw: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    adapter = _adapter(harness)
    settings = settings or Settings.load(raw.get("cwd") or None)
    try:
        event, operation = adapter.decode(raw)
    except Exception as exc:
        is_pre_tool = str(raw.get("hook_event_name") or raw.get("hookEventName")) == "PreToolUse" or "toolCall" in raw
        if is_pre_tool:
            tool_call = raw.get("toolCall") if isinstance(raw.get("toolCall"), Mapping) else {}
            tool_name = str(tool_call.get("name") or raw.get("tool_name") or "")
            # Workspace file mutations fail open so internal errors never paralyze code editing
            if tool_name in {"write_to_file", "replace_file_content", "multi_replace_file_content"}:
                return {"decision": "allow", "reason": f"Fail-open on inspection error: {type(exc).__name__}"}
            # For shell operations in Antigravity, ask user confirmation rather than hard blocking
            if harness == "antigravity":
                return {"decision": "ask", "reason": f"Jev inspection encountered an error ({type(exc).__name__}). Allow execution?"}
            reason = f"Jev could not inspect the pending tool operation: {type(exc).__name__}."
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                            "permissionDecisionReason": reason}}
        return {}
    result = Runtime(settings).dispatch(event, operation)
    return adapter.encode(event, result)


def _manual_authorize(args: argparse.Namespace, settings: Settings) -> int:
    reason_code = safety.critical_reason(args.command)
    if reason_code:
        print(f"Refusing authorization: operation violates invariant {reason_code}.", file=sys.stderr)
        return 2
    digest = operation_digest(args.tool, args.command, {"command": args.command})
    print("Pending operation")
    print(f"  Harness:  {args.harness}")
    print(f"  Workspace:{settings.workspace_root}")
    print(f"  Tool:     {args.tool}")
    print(f"  Command:  {args.command}")
    print(f"  Digest:   {digest}")
    if not args.confirm_digest or args.confirm_digest != digest:
        print("No rule saved. Re-run with --confirm-digest set to the displayed digest.")
        return 1
    Storage(settings.db_path).save_rule(
        pattern=args.command,
        tool_name=args.tool,
        scope="single_use",
        harness=args.harness,
        workspace_id=args.workspace_id,
        session_id=args.session_id,
        digest=digest,
        decision="allow",
        provenance="manual_cli",
        reason=args.reason,
    )
    print("Saved one-use Jev authorization. Native harness approvals still apply.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jev")
    sub = parser.add_subparsers(dest="command", required=True)
    hook = sub.add_parser("hook")
    hook.add_argument("--harness", choices=("antigravity", "codex"), required=True)
    doctor = sub.add_parser("doctor")
    doctor.add_argument("--cwd", default=".")
    migrate = sub.add_parser("migrate-legacy")
    migrate.add_argument("legacy_db", type=Path)
    migrate.add_argument("--cwd", default=".")
    authorize = sub.add_parser("authorize")
    authorize.add_argument("--harness", choices=("antigravity", "codex"), required=True)
    authorize.add_argument("--tool", required=True)
    authorize.add_argument("--command", required=True)
    authorize.add_argument("--workspace-id", required=True)
    authorize.add_argument("--session-id", default="")
    authorize.add_argument("--confirm-digest")
    authorize.add_argument("--reason", default="Manual one-use authorization")
    authorize.add_argument("--cwd", default=".")
    stats_p = sub.add_parser("stats", aliases=["telemetry"])
    stats_p.add_argument("--harness", choices=("antigravity", "codex"), default=None)
    stats_p.add_argument("--json", action="store_true", help="Output raw JSON")
    stats_p.add_argument("--cwd", default=".")
    mcp = sub.add_parser("mcp")
    mcp.add_argument("--cwd", default=".")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "hook":
        try:
            raw = json.loads(sys.stdin.read() or "{}")
            output = run_hook(args.harness, raw)
            sys.stdout.write(json.dumps(output, separators=(",", ":")))
            return 0
        except Exception as exc:
            print(f"Jev hook failed: {type(exc).__name__}", file=sys.stderr)
            return 1
    settings = Settings.load(getattr(args, "cwd", "."))
    if args.command == "doctor":
        print(format_report(settings))
        return 0
    if args.command in {"stats", "telemetry"}:
        storage = Storage(settings.db_path)
        data = storage.stats(harness=args.harness)
        if getattr(args, "json", False):
            print(json.dumps(data, indent=2))
        else:
            print("Jev Reflex & Decision Telemetry")
            print("================================")
            print(f"Database:        {settings.db_path}")
            print(f"Total Events:    {data['total_events']}")
            print(f"Avg Latency:     {data['avg_duration_ms']} ms")
            print("Harness Counts:  " + (", ".join(f"{k}: {v}" for k, v in data['harnesses'].items()) or "None"))
            print("Decisions:       " + (", ".join(f"{k}: {v}" for k, v in data['outcomes'].items()) or "None"))
            print("Features:        " + (", ".join(f"{k}: {v}" for k, v in data['features'].items()) or "None"))
        return 0
    if args.command == "migrate-legacy":
        storage = Storage(settings.db_path)
        backup = settings.data_root / "backups" / f"legacy-{args.legacy_db.name}.sqlite3"
        Storage.backup_existing(args.legacy_db, backup)
        print(json.dumps({"backup": str(backup), "imported_rules": storage.import_legacy(args.legacy_db)}))
        return 0
    if args.command == "authorize":
        return _manual_authorize(args, settings)
    if args.command == "mcp":
        from jev.transports.mcp import create_server
        create_server(settings).run(transport="stdio")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
