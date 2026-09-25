#!/usr/bin/env python3
"""
PreToolUse Hook: Jev Safety Gate for Antigravity.

Architecture:
  1. Fast-Path: File editing tools (write_to_file, etc.) are protected by IDE workspace
     history and git — allowed immediately (0ms).
  2. Invariant Shield: Unambiguously catastrophic actions (rm -rf, git reset --hard,
     disk format, force push) ALWAYS require explicit confirmation (force_ask).
  3. User Decision Memory: Checks SQLite for user-approved overrides (always / session).
  4. Jev Semantic Intent Judgment: Evaluates unknown shell commands using TypeSafe System One
     for routine development intent vs irreversible destruction risk.
  5. Permission Overrides: Surfaces "Save for session" and "Always allow" options when Jev flags.
"""

import sys
import os
import json
import urllib.request
import time
from pathlib import Path

# Load .agents/.env or .env if present
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import env_loader
    API_KEY, ENDPOINT, MODEL, BASE_HEADERS = env_loader.get_client_config()
except ImportError:
    API_KEY = os.environ.get("TYPESAFE_API_KEY", "") or os.environ.get("OPENROUTER_API_KEY", "")
    ENDPOINT = os.environ.get("TYPESAFE_ENDPOINT", "https://api.typesafe.ai/v1/systemone")
    MODEL = os.environ.get("JEV_MODEL", "jev-latest")
    BASE_HEADERS = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}

try:
    from safety_db import (
        check_decision,
        is_critical,
        save_decision,
        log_decision,
        clean_command_string,
        SKIP_CRITICAL_TOOLS,
    )
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    SKIP_CRITICAL_TOOLS = {"write_to_file", "replace_file_content", "multi_replace_file_content"}


def _log(msg: str):
    try:
        env_loader.log_debug("safety_gate", msg)
    except Exception:
        pass


def _decision_output(decision: str, reason: str, **extra) -> dict:
    out = {"decision": decision, "reason": reason}
    out.update(extra)
    return out


def is_sensitive_path(path_str: str) -> bool:
    """Checks if a file path targets sensitive system or credential storage."""
    p = path_str.lower().replace("\\", "/")
    sensitive_markers = [
        "/.ssh/", "/id_rsa", "/id_ed25519", "/.aws/credentials",
        "/etc/passwd", "/etc/shadow", "c:/windows/system32"
    ]
    return any(marker in p for marker in sensitive_markers)


def main():
    try:
        raw_input = sys.stdin.read()
        tool_call = json.loads(raw_input) if raw_input.strip() else {}
    except Exception:
        sys.exit(0)

    tool_call_obj   = tool_call.get("toolCall", {})
    tool_name       = tool_call_obj.get("name") or tool_call.get("tool_name", "")
    args            = tool_call_obj.get("args") or tool_call.get("args", {})
    command         = args.get("CommandLine", "") or args.get("command", "") or json.dumps(args)
    conversation_id = tool_call.get("conversationId", "")
    workspace_path  = (tool_call.get("workspacePaths") or [""])[0]

    # If no tool name, allow
    if not tool_name:
        print(json.dumps(_decision_output("allow", "")))
        sys.exit(0)

    # ── 1. FILE EDITING TOOLS FAST-PATH ─────────────────────────────────────────
    # File mutations within workspace are non-destructive in the shell sense and
    # protected by IDE undo / git. Allow immediately unless modifying credentials.
    if tool_name in SKIP_CRITICAL_TOOLS:
        target_file = args.get("TargetFile", "") or args.get("file_path", "")
        if target_file and is_sensitive_path(target_file):
            reason = f"[Jev Safety Gate] Modifying sensitive credential file: {target_file}"
            print(json.dumps(_decision_output("force_ask", reason)))
            sys.exit(0)
        # Normal workspace file editing is safe
        print(json.dumps(_decision_output("allow", "")))
        sys.exit(0)

    # ── 2. INVARIANT SAFETY SHIELD (deterministic catastrophic filter) ───────────
    if DB_AVAILABLE:
        critical, crit_reason = is_critical(tool_name, command)
        if critical:
            reason = (
                f"[Jev Safety Gate] ⛔ Critical operation — always requires confirmation: {crit_reason}. "
                f"Tool: {tool_name}"
            )
            _log(f"CRITICAL SHIELD: {crit_reason} | Tool: {tool_name} | Command: {command[:80]}")
            log_decision(conversation_id, tool_name, command, 0.0, 1.0,
                         "force_ask", "critical_shield", crit_reason)
            print(json.dumps(_decision_output("force_ask", reason)))
            sys.exit(0)

    # ── 3. USER DECISION MEMORY (SQLite Fast-Path) ──────────────────────────────
    if DB_AVAILABLE:
        db_decision, db_reason = check_decision(
            tool_name, command, conversation_id, workspace_path
        )
        if db_decision in ("allow", "deny"):
            _log(f"DB-HIT({db_decision}): {db_reason} | Tool: {tool_name} | Command: {command[:80]}")
            log_decision(conversation_id, tool_name, command, 1.0, 0.0,
                         db_decision, "decision_db", db_reason)
            print(json.dumps(_decision_output(db_decision, db_reason)))
            sys.exit(0)

    # ── 4. JEV SEMANTIC INTENT JUDGMENT ─────────────────────────────────────────
    # If no API key configured, fail-open for routine shell tasks (Shield already passed)
    if not API_KEY:
        print(json.dumps(_decision_output("allow", "")))
        sys.exit(0)

    clean_cmd = clean_command_string(command) if DB_AVAILABLE else command

    payload = {
        "model": MODEL,
        "state": f"Tool: {tool_name}\nCommand: {clean_cmd}",
        "questions": {
            "is_routine_dev_action": {
                "type": "noul",
                "instructions": (
                    "Is this a standard, routine development activity such as running tests, "
                    "building, linting, installing packages, checking git status, staging, "
                    "committing code, pushing branch updates, or running local scripts?"
                )
            },
            "irreversible_destruction_risk": {
                "type": "noul",
                "instructions": (
                    "Does this command irreversibly destroy unrecoverable data, wipe disk state "
                    "without backup, drop databases, or overwrite remote history?"
                )
            }
        }
    }

    start_time = time.time()

    try:
        req = urllib.request.Request(
            ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            headers=BASE_HEADERS,
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        answers          = data.get("answers", {})
        routine_score    = answers.get("is_routine_dev_action", {}).get("noul", 0.0)
        destruction_risk = answers.get("irreversible_destruction_risk", {}).get("noul", 0.0)
        latency_ms       = (time.time() - start_time) * 1000

        # Intercept conditions:
        # 1. High destruction risk (>= 0.50)
        # 2. Non-routine command with moderate risk (< 0.35 routine and >= 0.35 risk)
        should_intercept = (destruction_risk >= 0.50) or (routine_score < 0.35 and destruction_risk >= 0.35)

        if should_intercept:
            reason = (
                f"[Jev Safety Gate] Intercepted non-routine or risky command.\n"
                f"Destruction Risk: {destruction_risk:.2f} | Routine Score: {routine_score:.2f} ({latency_ms:.0f}ms)\n\n"
                f"Command: `{clean_cmd[:120]}`\n\n"
                f"Choose how to proceed:"
            )
            _log(
                f"INTERCEPTED: risk={destruction_risk:.2f}, routine={routine_score:.2f} "
                f"({latency_ms:.0f}ms) | Command: {clean_cmd[:80]}"
            )
            if DB_AVAILABLE:
                log_decision(conversation_id, tool_name, command, routine_score, destruction_risk,
                             "force_ask", "jev", reason[:200])

            # Surface permissionOverrides so user can save permanently or for session
            print(json.dumps({
                "decision": "force_ask",
                "reason": reason,
                "permissionOverrides": [
                    f"command({clean_cmd})",
                    f"session:command({clean_cmd})",
                    f"always:command({clean_cmd})",
                ]
            }))
            sys.exit(0)

        # Routine dev action: allow silently
        _log(
            f"ALLOWED: risk={destruction_risk:.2f}, routine={routine_score:.2f} "
            f"({latency_ms:.0f}ms) | Command: {clean_cmd[:80]}"
        )
        if DB_AVAILABLE:
            log_decision(conversation_id, tool_name, command, routine_score, destruction_risk,
                         "allow", "jev", "")
        print(json.dumps(_decision_output("allow", "")))
        sys.exit(0)

    except Exception as e:
        # On error/timeout, fail-open (critical shield already ran)
        _log(f"ERROR/TIMEOUT: {e} | Tool: {tool_name}")
        print(json.dumps(_decision_output("allow", "")))
        sys.exit(0)


if __name__ == "__main__":
    main()
