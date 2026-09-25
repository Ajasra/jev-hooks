#!/usr/bin/env python3
"""
PreInvocation Hook: Jev Speculative Fan-Out & Dual-Axis Confidence Arbiter for Antigravity (Proposal 21).

Evaluates 4-5 speculative questions in a single sub-120ms Jev request ($0.00008)
before the primary System 2 LLM begins reasoning.
Pre-fetches git status/diffs and test diagnostics to eliminate Turn-1 sequential tool stalls.
"""

import sys
import os
import json
import subprocess
import time
import urllib.request
from pathlib import Path

# Add hook directory to path for env_loader
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import env_loader
    API_KEY, ENDPOINT, MODEL, BASE_HEADERS = env_loader.get_client_config()
except ImportError:
    API_KEY = os.environ.get("TYPESAFE_API_KEY", "") or os.environ.get("OPENROUTER_API_KEY", "")
    ENDPOINT = os.environ.get("TYPESAFE_ENDPOINT", "https://api.typesafe.ai/v1/systemone")
    MODEL = os.environ.get("JEV_MODEL", "jev-latest")
    BASE_HEADERS = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}


def prefetch_git_state(cwd: str, max_lines: int = 80) -> str:
    """Safely runs non-destructive git status and concise diff."""
    try:
        status_proc = subprocess.run(
            ["cmd", "/c", "git status -s"],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3
        )
        status_out = (status_proc.stdout or "").strip()

        diff_proc = subprocess.run(
            ["cmd", "/c", "git diff -U2"],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=4
        )
        diff_out = (diff_proc.stdout or "").strip()

        if not status_out and not diff_out:
            return "Git Working Tree Clean (no uncommitted modifications)."

        lines = []
        if status_out:
            lines.append("### Git Status:\n" + status_out)
        if diff_out:
            diff_lines = diff_out.splitlines()
            if len(diff_lines) > max_lines:
                diff_truncated = "\n".join(diff_lines[:max_lines]) + f"\n... [Truncated: showing first {max_lines} lines of diff]"
            else:
                diff_truncated = diff_out
            lines.append("### Concise Git Diff (-U2):\n```diff\n" + diff_truncated + "\n```")

        return "\n\n".join(lines)
    except Exception as e:
        return f"Unable to prefetch git state: {e}"


def prefetch_test_state(cwd: str) -> str:
    """Inspects recent test status or runs a fast non-destructive test probe."""
    try:
        # Check for pytest lastfailed cache
        cache_path = Path(cwd) / ".pytest_cache" / "v" / "cache" / "lastfailed"
        if cache_path.exists():
            try:
                failed_data = json.loads(cache_path.read_text(encoding="utf-8"))
                if failed_data:
                    return f"### Last Failed Pytest Tests:\n" + "\n".join(f"- `{k}`" for k in list(failed_data.keys())[:10])
            except Exception:
                pass

        # If tests directory exists, run a quick pytest summary
        tests_dir = Path(cwd) / "tests"
        if tests_dir.exists():
            proc = subprocess.run(
                ["cmd", "/c", "pytest -q --tb=line"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=5
            )
            out = (proc.stdout or proc.stderr or "").strip()
            if out:
                summary_lines = [l for l in out.splitlines() if "failed" in l or "passed" in l or "error" in l]
                if summary_lines:
                    return "### Pytest Quick Summary:\n" + "\n".join(summary_lines[-5:])
                return "### Pytest Output (summary):\n" + "\n".join(out.splitlines()[-10:])
        return "No recent test failure records found in workspace."
    except Exception as e:
        return f"Unable to prefetch test state: {e}"


def evaluate_speculative_batch(user_prompt: str, cwd: str) -> dict:
    """
    Submits a single parallel 4-question speculative batch to Jev.
    Returns the parsed answer dictionary.
    """
    payload = {
        "model": MODEL,
        "state": f"Workspace Path: {cwd}\nDeveloper Instruction: {user_prompt}",
        "questions": {
            "needs_git_diff": {
                "type": "noul",
                "instructions": (
                    "Does resolving this developer instruction require reviewing recent uncommitted git modifications, "
                    "branch diffs, git status, or pending workspace edits?"
                )
            },
            "needs_test_log": {
                "type": "noul",
                "instructions": (
                    "Is the developer asking to diagnose a failed test, fix a test failure, inspect regression logs, "
                    "or verify unit/integration test outcomes?"
                )
            },
            "ambiguity_score": {
                "type": "score",
                "instructions": "Rate how underspecified, contradictory, or ambiguous the user's explicit objective is.",
                "criteria": [
                    "Completely explicit with concrete filenames, commands, or clear code targets",
                    "Clear high-level intent requiring standard architectural discovery and reasoning",
                    "Highly ambiguous, contradictory, or empty instruction requiring clarification before acting"
                ]
            },
            "suggested_action": {
                "type": "choice",
                "instructions": "What is the single most valuable pre-flight diagnostic evidence to fetch before the primary agent starts reasoning?",
                "criteria": {
                    "git_status_diff": "Fetch current git status and concise diff of modified files",
                    "test_status": "Fetch recent test failure reports or run targeted test probe",
                    "clarify": "Instruction is too vague; ask developer for clarification",
                    "none": "No speculative pre-fetch needed; proceed with standard agent reasoning"
                }
            }
        }
    }

    start_time = time.time()
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers=BASE_HEADERS,
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=4.0) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    latency_ms = (time.time() - start_time) * 1000
    answers = data.get("answers", {})
    answers["_latency_ms"] = latency_ms
    return answers


def arbitrate_and_assemble(answers: dict, user_prompt: str, cwd: str) -> dict:
    """
    Dual-Axis Confidence Arbiter:
    Maps Jev's answers to pre-flight context injections.
    """
    needs_git = answers.get("needs_git_diff", {}).get("noul", 0.0)
    needs_test = answers.get("needs_test_log", {}).get("noul", 0.0)
    ambiguity = answers.get("ambiguity_score", {}).get("score", 0.0)
    ambiguity_conf = answers.get("ambiguity_score", {}).get("confidence", 0.0)

    suggested = answers.get("suggested_action", {}).get("choice", "none")
    suggested_conf = answers.get("suggested_action", {}).get("confidence", 0.0)
    latency_ms = answers.get("_latency_ms", 0.0)

    sections = []
    actions_taken = []

    # 1. Speculative Git Prefetch (Noul >= 0.65 OR (choice match with Conf >= 0.70 and Noul >= 0.50))
    if needs_git >= 0.65 or (suggested == "git_status_diff" and suggested_conf >= 0.70 and needs_git >= 0.50):
        git_context = prefetch_git_state(cwd)
        sections.append(f"#### Speculatively Prefetched Git Context (P={needs_git:.2f}):\n{git_context}")
        actions_taken.append(f"git_prefetch (P={needs_git:.2f})")

    # 2. Speculative Test Diagnostics Prefetch (Noul >= 0.65 OR (choice match with Conf >= 0.70 and Noul >= 0.50))
    if needs_test >= 0.65 or (suggested == "test_status" and suggested_conf >= 0.70 and needs_test >= 0.50):
        test_context = prefetch_test_state(cwd)
        sections.append(f"#### Speculatively Prefetched Test Diagnostics (P={needs_test:.2f}):\n{test_context}")
        actions_taken.append(f"test_prefetch (P={needs_test:.2f})")

    # 3. High Ambiguity Notice (Score >= 1.75 and confidence >= 0.75)
    if ambiguity >= 1.75 and ambiguity_conf >= 0.75:
        sections.append(
            "> [!IMPORTANT]\n"
            f"> **Speculative Arbiter Advisory**: This user prompt was evaluated as highly ambiguous or underspecified "
            f"(Score={ambiguity:.1f}/2.0, Conf={ambiguity_conf:.2f}).\n\n"
            f"[CRITICAL AGENT INSTRUCTION: The user instruction '{user_prompt}' is completely underspecified. "
            "DO NOT browse the workspace, explore random files, or speculate on hidden context. "
            "You MUST immediately invoke your `ask_question` tool to render an interactive clarification modal for the user, "
            "blocking further execution until they select an option or specify what is broken! "
            "DO NOT call any other tools (no run_command, no grep_search, no view_file).]"
        )
        actions_taken.append(f"ambiguity_alert (Score={ambiguity:.1f})")

    # Log debug activation if available
    try:
        if actions_taken:
            msg = f"Actions: [{', '.join(actions_taken)}] (Latency: {latency_ms:.0f}ms) | Prompt: {user_prompt[:70]}..."
            env_loader.log_debug("speculative_router", msg)
    except Exception:
        pass

    if not sections:
        return {}

    badge = f"> **Jev Speculative Pre-Flight**: Attached speculative evidence ({', '.join(actions_taken)} in {latency_ms:.0f}ms)."
    agent_directive = (
        f"[INSTRUCTION FOR AGENT: The Jev Speculative Pre-Flight Arbiter evaluated this turn in {latency_ms:.0f}ms. "
        f"You MUST start your response with the badge `{badge}` so the user is informed. "
        "Use the prefetched evidence below directly without emitting redundant status tool calls.]\n\n"
    )

    full_message = f"<speculative_preflight>\n{badge}\n\n{agent_directive}" + "\n\n".join(sections) + "\n</speculative_preflight>"
    return {
        "injectSteps": [
            {
                "ephemeralMessage": full_message
            }
        ]
    }


def main():
    # CLI or Direct Invocation Support
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_prompt = sys.argv[2] if len(sys.argv) > 2 else "What are the uncommitted changes in this branch?"
        cwd = sys.argv[3] if len(sys.argv) > 3 else os.getcwd()
        print(f"Running standalone Speculative Fan-Out test on: '{test_prompt}' (cwd: {cwd})")
        ans = evaluate_speculative_batch(test_prompt, cwd)
        print("Raw Jev Answers:", json.dumps(ans, indent=2))
        res = arbitrate_and_assemble(ans, test_prompt, cwd)
        print("Hook Result Payload:", json.dumps(res, indent=2))
        return

    if not API_KEY:
        sys.exit(0)

    try:
        raw_input = sys.stdin.read()
        context = json.loads(raw_input) if raw_input.strip() else {}
    except Exception:
        sys.exit(0)

    user_prompt = context.get("prompt", "")
    workspace_paths = context.get("workspacePaths", [])
    cwd = workspace_paths[0] if workspace_paths else os.getcwd()

    if not user_prompt and "transcriptPath" in context:
        try:
            t_path = Path(context["transcriptPath"])
            if t_path.exists():
                for line in reversed(t_path.read_text(encoding="utf-8").splitlines()):
                    if line.strip():
                        try:
                            step = json.loads(line)
                            if step.get("type") == "USER_INPUT" or step.get("source") == "USER_EXPLICIT":
                                content = step.get("content", "")
                                if "<USER_REQUEST>" in content:
                                    content = content.split("<USER_REQUEST>")[1].split("</USER_REQUEST>")[0].strip()
                                user_prompt = content
                                break
                        except Exception:
                            continue
        except Exception:
            pass

    if not user_prompt:
        sys.exit(0)

    try:
        answers = evaluate_speculative_batch(user_prompt, cwd)
        result = arbitrate_and_assemble(answers, user_prompt, cwd)
        if result:
            print(json.dumps(result))
    except Exception:
        # Failsafe: exit 0 cleanly on network or parsing error
        sys.exit(0)


if __name__ == "__main__":
    main()
