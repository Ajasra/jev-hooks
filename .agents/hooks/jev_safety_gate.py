#!/usr/bin/env python3
"""
PreToolUse Hook: Jev Command Execution Safety Gate for Antigravity.
Evaluates proposed shell commands and file mutations against an ordered blast-radius rubric.
Exits with code 1 if high-impact or destructive operations are detected, halting execution
and prompting the developer for confirmation.
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
except ImportError:
    pass

TYPESAFE_API_KEY = os.environ.get("TYPESAFE_API_KEY", "")
TYPESAFE_ENDPOINT = os.environ.get("TYPESAFE_ENDPOINT", "https://api.typesafe.ai/v1/systemone")
JEV_MODEL = os.environ.get("JEV_MODEL", "jev-latest")

def main():
    try:
        raw_input = sys.stdin.read()
        tool_call = json.loads(raw_input) if raw_input.strip() else {}
    except Exception:
        sys.exit(0)

    tool_name = tool_call.get("tool_name", "")
    args = tool_call.get("args", {})
    command = args.get("CommandLine", "") or args.get("command", "") or json.dumps(args)

    # 1. Deterministic Hard-Rule Check: On Windows, enforce 'cmd /c'
    if tool_name == "run_command" and sys.platform == "win32":
        if not command.strip().startswith("cmd /c") and not command.strip().startswith("cmd.exe /c"):
            # Auto-wrap or warn
            sys.stderr.write("Rule Violation: Windows commands must be prefixed with 'cmd /c'.\n")

    if not TYPESAFE_API_KEY:
        sys.exit(0)

    # 2. Jev Blast Radius & Irreversibility Scoring
    payload = {
        "model": JEV_MODEL,
        "state": f"Tool: {tool_name}\nCommand/Args: {command}",
        "questions": {
            "blast_radius": {
                "type": "score",
                "instructions": "Rate the blast radius and potential irreversibility of this action.",
                "levels": {
                    "0": "Read-only inspection with zero persistent state mutation.",
                    "1": "Idempotent local mutation with automated rollback path.",
                    "2": "Non-idempotent mutation or network interaction requiring runtime isolation.",
                    "3": "High-risk operation: recursive deletions, credential access, or system environment changes."
                }
            },
            "is_destructive": {
                "type": "noul",
                "instructions": "Does this operation permanently destroy uncommitted work, delete directories, or format volumes?"
            }
        }
    }

    try:
        req = urllib.request.Request(
            TYPESAFE_ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {TYPESAFE_API_KEY}"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=0.8) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        answers = data.get("answers", {})
        blast_score = answers.get("blast_radius", {}).get("score", 0)
        is_destructive = answers.get("is_destructive", {}).get("noul", 0.0)

        # Halt execution if score >= 2 or is_destructive >= 0.7
        if blast_score >= 2 or is_destructive >= 0.7:
            sys.stderr.write(
                f"[Jev Safety Gate] Intercepted high-impact action: blast_radius={blast_score}, destructive_prob={is_destructive:.2f}.\n"
                "Halting for developer confirmation.\n"
            )
            # Exit code 1 signals Antigravity to pause and request user confirmation
            sys.exit(1)

    except Exception:
        # On error/timeout, fail-safe: allow command to proceed
        sys.exit(0)

    sys.exit(0)

if __name__ == "__main__":
    main()
