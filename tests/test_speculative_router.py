#!/usr/bin/env python3
"""
Test Suite for Proposal 21: Jev Speculative Fan-Out & Dual-Axis Confidence Arbiter.
Validates:
1. Multi-question batch evaluation against live Jev model.
2. Prefetching git state when needs_git_diff is elevated.
3. Prefetching test state when needs_test_log is elevated.
4. Ambiguity scoring and warning generation.
5. Antigravity PreInvocation injectSteps schema compliance.
"""

import sys
import os
import json
import time
from pathlib import Path

# Add hook directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".agents" / "hooks"))
import env_loader
import jev_speculative_router

CWD = str(Path(__file__).resolve().parent.parent)


def test_git_prefetch_trigger():
    print("\n--- Test 1: Speculative Git Diff Prefetch ---")
    prompt = "Review my recent uncommitted changes and show me git diff"
    answers = jev_speculative_router.evaluate_speculative_batch(prompt, CWD)
    print("  Jev Batch Latency:", f"{answers.get('_latency_ms', 0):.0f}ms")
    needs_git = answers.get("needs_git_diff", {}).get("noul", 0.0)
    print(f"  needs_git_diff Noul: {needs_git:.2f}")

    result = jev_speculative_router.arbitrate_and_assemble(answers, prompt, CWD)
    assert needs_git >= 0.50, f"Expected needs_git_diff >= 0.50, got {needs_git}"
    assert "injectSteps" in result, "Expected injectSteps in arbiter result"
    msg = result["injectSteps"][0]["ephemeralMessage"]
    assert "git_prefetch" in msg or "Git Context" in msg, "Expected git prefetch banner in message"
    print("  [PASS] Git diff correctly speculatively identified and prefetched.")


def test_test_log_prefetch_trigger():
    print("\n--- Test 2: Speculative Test Diagnostics Prefetch ---")
    prompt = "Why is test_gate_eval failing? Look at the test output and fix the regression."
    answers = jev_speculative_router.evaluate_speculative_batch(prompt, CWD)
    needs_test = answers.get("needs_test_log", {}).get("noul", 0.0)
    print(f"  needs_test_log Noul: {needs_test:.2f}")

    result = jev_speculative_router.arbitrate_and_assemble(answers, prompt, CWD)
    assert needs_test >= 0.50, f"Expected needs_test_log >= 0.50, got {needs_test}"
    assert "injectSteps" in result, "Expected injectSteps in arbiter result"
    msg = result["injectSteps"][0]["ephemeralMessage"]
    assert "test_prefetch" in msg or "Test Diagnostics" in msg, "Expected test prefetch banner in message"
    print("  [PASS] Test diagnostics correctly speculatively identified and prefetched.")


def test_ambiguity_scoring():
    print("\n--- Test 3: Ambiguity Scoring on Underspecified Prompt ---")
    prompt = "it broke, do something"
    answers = jev_speculative_router.evaluate_speculative_batch(prompt, CWD)
    ambiguity = answers.get("ambiguity_score", {}).get("score", 0.0)
    conf = answers.get("ambiguity_score", {}).get("confidence", 0.0)
    print(f"  ambiguity_score: {ambiguity:.2f} (Confidence: {conf:.2f})")

    assert ambiguity >= 1.0, f"Expected ambiguity score >= 1.0 on vague prompt, got {ambiguity}"
    print("  [PASS] Ambiguity correctly rated high for underspecified prompt.")


def test_benign_prompt_clean_pass():
    print("\n--- Test 4: Benign Prompt (No Stalls, Clean Pass) ---")
    prompt = "Please explain the architecture of the Jev System One model in markdown."
    answers = jev_speculative_router.evaluate_speculative_batch(prompt, CWD)
    needs_git = answers.get("needs_git_diff", {}).get("noul", 0.0)
    needs_test = answers.get("needs_test_log", {}).get("noul", 0.0)
    print(f"  needs_git: {needs_git:.2f}, needs_test: {needs_test:.2f}")

    result = jev_speculative_router.arbitrate_and_assemble(answers, prompt, CWD)
    assert needs_git < 0.50, f"Expected low git need for prose explanation, got {needs_git}"
    assert needs_test < 0.50, f"Expected low test need for prose explanation, got {needs_test}"
    print("  [PASS] Benign prompt does not trigger unnecessary prefetching.")


def test_agent_context_injection():
    print("\n--- Test 5: Custom Agent Context Injection ---")
    mock_context = {
        "agent": "Security & Code Hygiene Auditor",
        "workspacePaths": [CWD]
    }
    agent_summary = jev_speculative_router.get_agent_summary(CWD, mock_context)
    assert agent_summary == "Security & Code Hygiene Auditor"
    prompt = "audit this codebase"
    answers = jev_speculative_router.evaluate_speculative_batch(prompt, CWD, mock_context)
    print("  Jev Batch Latency with Agent Context:", f"{answers.get('_latency_ms', 0):.0f}ms")
    needs_git = answers.get("needs_git_diff", {}).get("noul", 0.0)
    print(f"  needs_git_diff Noul for Auditor: {needs_git:.2f}")
    assert needs_git >= 0.50
    print("  [PASS] Agent context injected and correctly informed speculative judgment.")


def test_active_document_ambiguity_calibration():
    print("\n--- Test 6: Active Document Context Ambiguity Calibration ---")
    prompt = "lets review our Knowledge item proposal. Analyze it once more."
    active_doc = str(Path(CWD) / "proposals" / "03_PROPOSAL_C_KNOWLEDGE_ITEM_MATCHER.md")
    
    # Without active doc (simulating previous bug)
    answers_without = jev_speculative_router.evaluate_speculative_batch(prompt, CWD)
    score_without = answers_without.get("ambiguity_score", {}).get("score", 0.0)
    
    # With active doc (new behavior)
    answers_with = jev_speculative_router.evaluate_speculative_batch(
        prompt, CWD, active_doc=active_doc
    )
    score_with = answers_with.get("ambiguity_score", {}).get("score", 0.0)
    print(f"  Score without active doc: {score_without:.2f} -> Score with active doc: {score_with:.2f}")

    # Arbiter should NOT trigger ambiguity alert when active doc is present and continuation matches
    result = jev_speculative_router.arbitrate_and_assemble(
        answers_with, prompt, CWD, active_doc=active_doc
    )
    msg = result.get("injectSteps", [{}])[0].get("ephemeralMessage", "")
    assert "ambiguity_alert" not in msg, "Ambiguity alert should NOT be triggered for contextual proposal review"
    print("  [PASS] Active document successfully suppresses false positive ambiguity alert.")


def test_semantic_continuation_detection():
    print("\n--- Test 7: Jev Machine-Native Continuation Detection ---")
    active_doc = str(Path(CWD) / "proposals" / "03_PROPOSAL_C_KNOWLEDGE_ITEM_MATCHER.md")

    # Follow-up continuation
    ans_cont = jev_speculative_router.evaluate_speculative_batch(
        "apply edits to proposal", CWD, active_doc=active_doc
    )
    noul_cont = ans_cont.get("is_continuation", {}).get("noul", 0.0)
    print(f"  'apply edits to proposal' is_continuation Noul: {noul_cont:.2f}")
    assert noul_cont >= 0.65, f"Expected is_continuation >= 0.65, got {noul_cont}"

    # Vague prompt lacking context
    ans_vague = jev_speculative_router.evaluate_speculative_batch(
        "it broke, do something", CWD
    )
    noul_vague = ans_vague.get("is_continuation", {}).get("noul", 0.0)
    print(f"  'it broke, do something' is_continuation Noul: {noul_vague:.2f}")
    assert noul_vague < 0.50, f"Expected is_continuation < 0.50, got {noul_vague}"

    print("  [PASS] Jev successfully discriminates continuations without hardcoded lists.")


def run_all():
    api_key, endpoint, model, _ = env_loader.get_client_config()
    print("=== Testing Proposal 21: Speculative Fan-Out & Dual-Axis Arbiter ===")
    print(f"Model: {model} | Endpoint: {endpoint}")
    test_git_prefetch_trigger()
    test_test_log_prefetch_trigger()
    test_ambiguity_scoring()
    test_benign_prompt_clean_pass()
    test_agent_context_injection()
    test_active_document_ambiguity_calibration()
    test_semantic_continuation_detection()
    print("\n=== ALL SPECULATIVE ROUTER TESTS PASSED ===")


if __name__ == "__main__":
    run_all()
