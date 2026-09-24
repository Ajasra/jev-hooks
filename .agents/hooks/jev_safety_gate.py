#!/usr/bin/env python3
"""
PreToolUse Hook: Jev Command Execution Safety Gate for Antigravity.

Decision pipeline (in order):
  1. Critical Shield  — hard patterns (rm -rf, git reset --hard, etc.) always force_ask
  2. Decision DB      — permanent ('always') or session-scoped pre-approved rules → allow/deny
  3. Jev Scoring      — Jev blast-radius & destructive-prob scoring for everything else
  4. DB Write-back    — when user chooses 'save for session' or 'save always' in the modal,
                        the gate persists the rule so future calls skip Jev entirely.
"""

import sys
import os
import json
import urllib.request
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
    )
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False


def _log(msg: str):
    try:
        env_loader.log_debug("safety_gate", msg)
    except Exception:
        pass


def _decision_output(decision: str, reason: str, **extra) -> dict:
    out = {"decision": decision, "reason": reason}
    out.update(extra)
    return out


def main():
    try:
        raw_input = sys.stdin.read()
        tool_call = json.loads(raw_input) if raw_input.strip() else {}
    except Exception:
        sys.exit(0)

    tool_call_obj = tool_call.get("toolCall", {})
    tool_name     = tool_call_obj.get("name") or tool_call.get("tool_name", "")
    args          = tool_call_obj.get("args") or tool_call.get("args", {})
    command       = args.get("CommandLine", "") or args.get("command", "") or json.dumps(args)
    conversation_id = tool_call.get("conversationId", "")
    workspace_path  = (tool_call.get("workspacePaths") or [""])[0]

    # If no tool name, allow
    if not tool_name:
        print(json.dumps(_decision_output("allow", "")))
        sys.exit(0)

    # ── 1. CRITICAL SHIELD (deterministic, cannot be bypassed) ──────────────────
    if DB_AVAILABLE:
        critical, crit_reason = is_critical(tool_name, command)
        if critical:
            reason = (
                f"[Jev Safety Gate] ⛔ Critical operation — always requires confirmation: {crit_reason}. "
                f"Tool: {tool_name}"
            )
            _log(f"CRITICAL SHIELD: {crit_reason} | Tool: {tool_name} | Args: {command[:80]}")
            log_decision(conversation_id, tool_name, command, 4.0, 1.0,
                         "force_ask", "critical_shield", crit_reason)
            print(json.dumps(_decision_output("force_ask", reason)))
            sys.exit(0)

    # ── 2. DECISION DB FAST-PATH ────────────────────────────────────────────────
    if DB_AVAILABLE:
        db_decision, db_reason = check_decision(
            tool_name, command, conversation_id, workspace_path
        )
        if db_decision in ("allow", "deny"):
            _log(f"DB-HIT({db_decision}): {db_reason} | Tool: {tool_name} | Args: {command[:80]}")
            log_decision(conversation_id, tool_name, command, 0, 0,
                         db_decision, "decision_db", db_reason)
            print(json.dumps(_decision_output(db_decision, db_reason)))
            sys.exit(0)

    # ── 3. JEV SCORING ──────────────────────────────────────────────────────────
    if not API_KEY:
        print(json.dumps(_decision_output("allow", "")))
        sys.exit(0)

    payload = {
        "model": MODEL,
        "state": f"Tool: {tool_name}\nCommand/Args: {command}",
        "questions": {
            "blast_radius": {
                "type": "score",
                "instructions": "Rate the blast radius and potential irreversibility of this action.",
                "criteria": [
                    "Read-only inspection with zero persistent state mutation.",
                    "Idempotent local mutation with automated rollback path.",
                    "Non-idempotent mutation or network interaction requiring runtime isolation.",
                    "High-risk operation: recursive deletions, credential access, or system environment changes."
                ]
            },
            "is_destructive": {
                "type": "noul",
                "instructions": "Does this operation permanently destroy uncommitted work, delete directories, or format volumes?"
            }
        }
    }

    import time
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

        answers        = data.get("answers", {})
        blast_score    = answers.get("blast_radius", {}).get("score", 0)
        is_destructive = answers.get("is_destructive", {}).get("noul", 0.0)
        latency_ms     = (time.time() - start_time) * 1000

        # ── 4. ESCALATE or ALLOW ─────────────────────────────────────────────
        if blast_score >= 2 or is_destructive >= 0.7:
            clean_cmd = clean_command_string(command) if DB_AVAILABLE else command

            reason = (
                f"[Jev Safety Gate] Intercepted high-impact action — "
                f"blast_radius={blast_score:.2f}, destructive_prob={is_destructive:.2f}.\n\n"
                f"Tool: `{tool_name}`\n"
                f"Command: `{clean_cmd[:120]}`\n\n"
                f"Choose how to proceed:"
            )
            _log(
                f"INTERCEPTED: blast_radius={blast_score:.2f}, destructive_prob={is_destructive:.2f} "
                f"({latency_ms:.0f}ms) | Tool: {tool_name} | Args: {command[:80]}"
            )
            log_decision(conversation_id, tool_name, command, blast_score, is_destructive,
                         "force_ask", "jev", reason[:200])

            # Emit force_ask with structured permissionOverrides carrying the metadata
            # so the runtime can offer "Save for session" / "Save always" choices.
            print(json.dumps({
                "decision": "force_ask",
                "reason": reason,
                # permissionOverrides names encode the available save-back actions
                # that the AGY runtime surfaces as buttons in the confirmation modal.
                "permissionOverrides": [
                    f"command({clean_cmd})",                         # once — just this call
                    f"session:command({clean_cmd})",                 # save for this session
                    f"always:command({clean_cmd})",                  # save permanently
                ]
            }))
            sys.exit(0)

        # Safe: allow
        _log(
            f"ALLOWED: blast_radius={blast_score:.2f}, destructive_prob={is_destructive:.2f} "
            f"({latency_ms:.0f}ms) | Tool: {tool_name} | Args: {command[:80]}"
        )
        log_decision(conversation_id, tool_name, command, blast_score, is_destructive,
                     "allow", "jev", "")
        print(json.dumps(_decision_output("allow", "")))
        sys.exit(0)

    except Exception as e:
        # On error/timeout, fail-open
        _log(f"ERROR/TIMEOUT: {e} | Tool: {tool_name}")
        print(json.dumps(_decision_output("allow", "")))
        sys.exit(0)


if __name__ == "__main__":
    main()
