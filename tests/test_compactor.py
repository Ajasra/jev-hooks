#!/usr/bin/env python3
"""
Test Suite for Jev Verbatim Trajectory Compactor (Proposal A).
Validates:
1. Zero-rewrite verbatim preservation of user prompts and discourse.
2. Pinned boundary preservation (root prompt + trailing recency window).
3. Selective pruning of superseded historical tool outputs.
4. Compression ratio and token efficiency metrics.
"""

import sys
import json
import time
from pathlib import Path

# Add .agents/hooks to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".agents" / "hooks"))
import env_loader
import jev_compactor

def build_realistic_session():
    """Builds a realistic 12-turn refactoring session with large tool outputs."""
    return [
        {
            "role": "user",
            "content": "Refactor the authentication layer to use JWT tokens and clean up legacy session routes."
        },
        {
            "role": "assistant",
            "content": "Inspecting current auth implementation.",
            "tool_calls": [
                {
                    "id": "call_inspect_auth",
                    "name": "view_file",
                    "arguments": {"AbsolutePath": "backend/auth/legacy.py"},
                    "result": "def legacy_auth():\n" + "    # legacy token verification logic\n" * 150
                }
            ]
        },
        {
            "role": "user",
            "content": "Run tests before making changes to establish our baseline."
        },
        {
            "role": "assistant",
            "content": "Running test suite.",
            "tool_calls": [
                {
                    "id": "call_baseline_test",
                    "name": "run_command",
                    "arguments": {"CommandLine": "pytest tests/test_auth.py"},
                    "result": "=== 42 passed, 2 skipped in 3.12s ===\n" + "[PASS] test_token_validation\n" * 80
                }
            ]
        },
        {
            "role": "user",
            "content": "Now replace the legacy auth with the new JWT handler."
        },
        {
            "role": "assistant",
            "content": "Applying changes to auth layer.",
            "tool_calls": [
                {
                    "id": "call_apply_jwt",
                    "name": "replace_file_content",
                    "arguments": {"TargetFile": "backend/auth/jwt.py", "Instruction": "Add JWT handler"},
                    "result": "Successfully updated backend/auth/jwt.py with 48 lines replaced."
                }
            ]
        },
        {
            "role": "user",
            "content": "Search for any remaining references to legacy_auth across the repo."
        },
        {
            "role": "assistant",
            "content": "Searching for legacy references.",
            "tool_calls": [
                {
                    "id": "call_grep_legacy",
                    "name": "grep_search",
                    "arguments": {"Query": "legacy_auth", "SearchPath": "backend/"},
                    "result": "backend/routes/auth.py:14: legacy_auth()\n" * 40
                }
            ]
        },
        {
            "role": "assistant",
            "content": "All legacy references have been replaced. Now validating the new JWT test suite.",
            "tool_calls": [
                {
                    "id": "call_verify_jwt",
                    "name": "run_command",
                    "arguments": {"CommandLine": "pytest tests/test_jwt.py"},
                    "result": "=== 55 passed in 2.84s ===\n" + "[PASS] test_jwt_signature\n" * 60
                }
            ]
        },
        {
            "role": "user",
            "content": "What is our current test coverage and are all endpoints secure?"
        },
        {
            "role": "assistant",
            "content": "Test coverage is at 94.2% across the authentication module.",
            "tool_calls": [
                {
                    "id": "call_check_coverage",
                    "name": "run_command",
                    "arguments": {"CommandLine": "pytest --cov=backend/auth"},
                    "result": "Coverage report: 94.2% statements covered."
                }
            ]
        },
        {
            "role": "user",
            "content": "Great, please prepare the final commit."
        }
    ]

def run_tests():
    print("=" * 70)
    print(" JEV VERBATIM TRANSCRIPT COMPACTOR TEST SUITE (Proposal A)")
    print("=" * 70)

    api_key, endpoint, model, _ = env_loader.get_client_config()
    print(f"[*] API Key Present: {bool(api_key)}")
    print(f"[*] Endpoint: {endpoint}")
    print(f"[*] Model: {model}")
    print("-" * 70)

    session = build_realistic_session()
    raw_json = json.dumps(session)
    initial_chars = len(raw_json)
    initial_turns = len(session)
    print(f"[*] Input Transcript: {initial_turns} turns, {initial_chars:,} characters.")

    # Record all original user messages for strict verbatim equality assertion
    original_user_prompts = [
        msg["content"] for msg in session if msg.get("role") == "user"
    ]

    print("[*] Dispatching parallel dual-Noul evaluation to Jev...")
    start_time = time.time()
    compacted = jev_compactor.compact_trajectory(session)
    elapsed = time.time() - start_time

    compacted_json = json.dumps(compacted)
    final_chars = len(compacted_json)
    reduction = (1 - final_chars / initial_chars) * 100

    print(f"[+] Compaction completed in {elapsed:.2f}s (P95 latency target: <2.0s).")
    print(f"[+] Output Size: {initial_chars:,} chars -> {final_chars:,} chars.")
    print(f"[+] Total Size Reduction: {reduction:.1f}%.")

    # Validation Checks
    print("\n--- Verification Assertions ---")

    # 1. Verbatim Discourse Integrity
    compacted_user_prompts = [
        msg["content"] for msg in compacted if msg.get("role") == "user"
    ]
    assert original_user_prompts == compacted_user_prompts, "FAIL: User discourse was altered!"
    print("[PASS] User discourse preserved 100% verbatim (zero rewrites/hallucinations).")

    # 2. Pinned Root Turn Integrity
    assert compacted[0] == session[0], "FAIL: Root prompt was modified!"
    print("[PASS] Root architectural prompt pinned and preserved.")

    # 3. Recency Window Integrity
    recent_count = jev_compactor.PRESERVE_RECENT_MESSAGES
    assert compacted[-recent_count:] == session[-recent_count:], "FAIL: Recent window was modified!"
    print(f"[PASS] Trailing recency window ({recent_count} messages) preserved verbatim.")

    # 4. Surgical Tool Pruning
    # Verify that historical tool outputs were compacted to receipts
    truncated_found = False
    for msg in compacted[:-recent_count]:
        for call in msg.get("tool_calls", []):
            res = str(call.get("result", ""))
            if "Jev Compactor: Result truncated" in res:
                truncated_found = True
                print(f"[PASS] Tool '{call['id']}' ({call['name']}) pruned to concise receipt.")
    
    assert truncated_found, "Expected at least one historical tool output to be truncated."
    print("\n[SUCCESS] All compactor validation assertions passed.")

if __name__ == "__main__":
    run_tests()
