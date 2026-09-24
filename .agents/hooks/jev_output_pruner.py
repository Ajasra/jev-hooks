#!/usr/bin/env python3
"""
PostToolUse Hook: Jev Real-Time Log & Stream Pruner for Antigravity.
Intercepts completed tool outputs exceeding 1,000 characters (e.g. test suites, build logs, greps).
If the execution succeeded cleanly, prunes routine logs into a concise structural stub,
preventing context pollution before results are serialized into session trajectories.
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

def main():
    try:
        raw_input = sys.stdin.read()
        payload = json.loads(raw_input) if raw_input.strip() else {}
    except Exception:
        sys.exit(0)

    stdout = payload.get("stdout", "")
    exit_code = payload.get("exit_code", 0)

    # Only prune outputs that are large (> 1,000 chars)
    if len(stdout) < 1000 or not API_KEY:
        sys.exit(0)

    jev_payload = {
        "model": MODEL,
        "state": f"Exit Code: {exit_code}\nOutput Head:\n{stdout[:1500]}\nOutput Tail:\n{stdout[-1500:]}",
        "questions": {
            "is_clean_success": {
                "type": "noul",
                "instructions": "Does this terminal output represent a clean, non-failing execution where all tests/builds passed without actionable errors?"
            },
            "contains_stack_trace": {
                "type": "noul",
                "instructions": "Does this output contain an unhandled exception, failing test assertion, or actionable error trace?"
            }
        }
    }

    try:
        req = urllib.request.Request(
            ENDPOINT,
            data=json.dumps(jev_payload).encode("utf-8"),
            headers=BASE_HEADERS,
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=0.8) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        answers = data.get("answers", {})
        is_clean = answers.get("is_clean_success", {}).get("noul", 0.0)
        has_errors = answers.get("contains_stack_trace", {}).get("noul", 0.0)

        # If it is a clean success with no stack trace, prune the log body
        if is_clean >= 0.75 and has_errors < 0.25:
            pruned_stdout = (
                f"{stdout[:250]}\n\n"
                f"[... Jev Stream Pruner: Execution succeeded cleanly. {len(stdout) - 500:,} non-failing log characters omitted ...]\n\n"
                f"{stdout[-250:]}"
            )
            # Output modified result back to Antigravity runtime
            print(json.dumps({"stdout": pruned_stdout}))
    except Exception:
        # On timeout or error, leave output intact
        sys.exit(0)

if __name__ == "__main__":
    main()
