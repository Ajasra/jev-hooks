#!/usr/bin/env python3
"""
PreInvocation Hook: Jev Speculative Fan-Out & Dual-Axis Confidence Arbiter for Antigravity (Proposal 21).

Evaluates 4-5 speculative questions in a single sub-120ms Jev request ($0.00008)
before the primary System 2 LLM begins reasoning.
Pre-fetches git status/diffs and test diagnostics to eliminate Turn-1 sequential tool stalls.
"""

import sys
import os
import re
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


def get_project_summary(cwd: str) -> str:
    """Extracts a compact 1-line summary of the workspace identity from README or project configs."""
    try:
        readme = Path(cwd) / "README.md"
        if readme.exists():
            for line in readme.read_text(encoding="utf-8", errors="ignore").splitlines()[:8]:
                line = line.strip().lstrip("#").strip()
                if line and not line.startswith("!") and not line.startswith("["):
                    return line[:120]
        pkg = Path(cwd) / "package.json"
        if pkg.exists():
            data = json.loads(pkg.read_text(encoding="utf-8"))
            desc = data.get("description") or data.get("name")
            if desc:
                return desc[:120]
        pyproject = Path(cwd) / "pyproject.toml"
        if pyproject.exists():
            for line in pyproject.read_text(encoding="utf-8", errors="ignore").splitlines():
                if "description" in line and "=" in line:
                    return line.split("=", 1)[1].strip(" '\"")[:120]
    except Exception:
        pass
    return Path(cwd).name


def get_git_branch(cwd: str) -> str:
    """Fast zero-subprocess extraction of current git branch from .git/HEAD."""
    try:
        head = Path(cwd) / ".git" / "HEAD"
        if head.exists():
            content = head.read_text(encoding="utf-8", errors="ignore").strip()
            if content.startswith("ref: refs/heads/"):
                return content.replace("ref: refs/heads/", "")
            return content[:8]
    except Exception:
        pass
    return ""


def get_agent_summary(cwd: str, context: dict = None) -> str:
    """
    Extracts a concise 1-line agent persona/role from context or agent definition files
    (e.g., AGENTS.md, AGENT.md, GEMINI.md, or hook context metadata).
    """
    if context:
        for key in ("agentName", "agent", "subagent", "role", "persona", "customAgent"):
            val = context.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()[:100]
            elif isinstance(val, dict) and "name" in val:
                return str(val["name"])[:100]

    search_paths = [
        Path(cwd) / "AGENTS.md",
        Path(cwd) / ".agents" / "AGENTS.md",
        Path(cwd) / "AGENT.md",
        Path(cwd) / ".agents" / "AGENT.md",
        Path(cwd) / "GEMINI.md",
        Path(cwd) / ".agents" / "GEMINI.md",
    ]
    for p in search_paths:
        try:
            if p.exists():
                for line in p.read_text(encoding="utf-8", errors="ignore").splitlines()[:10]:
                    clean = line.strip().lstrip("#").strip()
                    if clean and not clean.startswith("!") and not clean.startswith("["):
                        return clean[:100]
        except Exception:
            pass

    return ""


def is_bare_link(prompt: str) -> bool:
    """Detects if prompt is just a raw URL without accompanying instructions."""
    p = prompt.strip().strip("<>\"'")
    if " " in p or "\n" in p:
        return False
    return p.startswith("http://") or p.startswith("https://") or p.startswith("www.")


def is_informational_question(prompt: str) -> bool:
    """Detects conceptual/architectural questions so they are not falsely treated as ambiguous tasks."""
    p = prompt.lower().strip()
    prefixes = ("what", "how", "why", "who", "when", "where", "can you", "explain", "describe", "tell me", "is there", "are there", "does", "do we", "should we")
    return any(p.startswith(w) for w in prefixes) or p.endswith("?")


def extract_context_from_transcript(transcript_path: Path) -> dict:
    """
    Extracts current prompt, active editor document, open documents,
    and prior conversation turns from Antigravity transcript.jsonl.
    """
    if not transcript_path or not transcript_path.exists():
        return {}

    current_prompt = ""
    active_doc = ""
    open_docs = []
    prior_prompt = ""
    found_current = False

    try:
        lines = transcript_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                step = json.loads(line)
            except Exception:
                continue

            is_user = (step.get("type") == "USER_INPUT" or step.get("source") == "USER_EXPLICIT")
            content = step.get("content", "")

            if is_user and not found_current:
                found_current = True
                if "<USER_REQUEST>" in content:
                    req_match = re.search(r"<USER_REQUEST>(.*?)</USER_REQUEST>", content, re.DOTALL)
                    current_prompt = req_match.group(1).strip() if req_match else content.strip()
                else:
                    current_prompt = content.strip()

                if "<ADDITIONAL_METADATA>" in content:
                    meta_match = re.search(r"<ADDITIONAL_METADATA>(.*?)</ADDITIONAL_METADATA>", content, re.DOTALL)
                    if meta_match:
                        meta = meta_match.group(1)
                        doc_match = re.search(r"Active Document:\s*([^\r\n]+)", meta)
                        if doc_match:
                            raw_doc = doc_match.group(1).strip()
                            active_doc = re.sub(r"\s*\(LANGUAGE_[A-Z_]+\)", "", raw_doc).strip()

                        open_docs_match = re.search(r"Other open documents:\s*(.*?)(?:No browser|Cursor|$)", meta, re.DOTALL)
                        if open_docs_match:
                            for d_line in open_docs_match.group(1).strip().splitlines():
                                d_clean = re.sub(r"\s*\(LANGUAGE_[A-Z_]+\)", "", d_line.strip().lstrip("-").strip()).strip()
                                if d_clean and d_clean != active_doc and d_clean not in open_docs:
                                    open_docs.append(d_clean)
                continue

            if is_user and found_current and not prior_prompt:
                if "<USER_REQUEST>" in content:
                    req_match = re.search(r"<USER_REQUEST>(.*?)</USER_REQUEST>", content, re.DOTALL)
                    prior_prompt = req_match.group(1).strip() if req_match else content.strip()
                else:
                    prior_prompt = content.strip()
                break
    except Exception:
        pass

    return {
        "current_prompt": current_prompt,
        "active_document": active_doc,
        "open_documents": open_docs,
        "prior_prompt": prior_prompt
    }


def evaluate_speculative_batch(
    user_prompt: str,
    cwd: str,
    context: dict = None,
    prior_turn: str = "",
    active_doc: str = "",
    open_docs: list = None
) -> dict:
    """
    Submits a single parallel 4-question speculative batch to Jev with project, agent,
    open editor document, and conversational recency context.
    Returns the parsed answer dictionary.
    """
    project_desc = get_project_summary(cwd)
    branch = get_git_branch(cwd)
    branch_str = f" (Branch: {branch})" if branch else ""
    agent_desc = get_agent_summary(cwd, context)
    agent_str = f"\nActive Agent: {agent_desc}" if agent_desc else ""
    prior_str = f"\nPrior Turn Request: {prior_turn}" if prior_turn else ""
    active_doc_str = f"\nActive Editor Document: {active_doc}" if active_doc else ""
    open_docs_str = f"\nOther Open Documents: {', '.join(open_docs[:3])}" if open_docs else ""

    state = (
        f"Project Identity: {project_desc}\n"
        f"Workspace Path: {cwd}{branch_str}"
        f"{agent_str}"
        f"{active_doc_str}"
        f"{open_docs_str}"
        f"{prior_str}\n"
        f"Developer Prompt: {user_prompt}"
    )

    payload = {
        "model": MODEL,
        "state": state,
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
            "is_continuation": {
                "type": "noul",
                "instructions": (
                    "Does this prompt represent an explicit affirmative confirmation, approval, or constructive next step continuation "
                    "(e.g. 'yes', 'proceed', 'apply edits', 'refine proposal', 'commit', 'looks good') "
                    "that affirmatively agrees or advances existing work, as opposed to an unguided error report, isolated question, or new unanchored task?"
                )
            },
            "ambiguity_score": {
                "type": "score",
                "instructions": (
                    "Rate how underspecified, contradictory, or unguided the developer prompt is in the context of the workspace, "
                    "open editor document, and prior conversational turn. "
                    "Informational questions, requests referring to the active file/proposal/code, and standard iterative continuations "
                    "(e.g., 'apply edits', 'review proposal', 'update docs', 'run tests') are clear and unambiguous (score 0 or 1). "
                    "Only commands that genuinely lack context or target in the workspace (e.g. 'it broke', 'do something', or bare links without instructions) receive score 2."
                ),
                "criteria": [
                    "Completely explicit request, clear informational question, or refers to the active document/project context",
                    "Standard engineering request, review, or workflow requiring normal code discovery",
                    "Underspecified action commands that lack context or target (e.g. 'it broke', 'do something', or bare links without instructions)"
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


AFFIRMATIVE_CONTINUATIONS = {
    "yes", "yes, implement", "yes, please", "proceed", "continue", "go ahead",
    "do it", "approved", "ok", "okay", "sure", "yep", "lgtm", "yes implement"
}


def is_affirmative_continuation(prompt: str) -> bool:
    """Zero-latency local fallback for micro-affirmations."""
    clean = re.sub(r"[^\w\s]", "", prompt.lower()).strip()
    return clean in {re.sub(r"[^\w\s]", "", w) for w in AFFIRMATIVE_CONTINUATIONS}


def arbitrate_and_assemble(
    answers: dict,
    user_prompt: str,
    cwd: str,
    conversation_id: str = "",
    active_doc: str = "",
    prior_turn: str = ""
) -> dict:
    """
    Dual-Axis Confidence Arbiter:
    Maps Jev's answers to pre-flight context injections and logs to SQLite for active tuning.
    """
    needs_git = answers.get("needs_git_diff", {}).get("noul", 0.0)
    needs_test = answers.get("needs_test_log", {}).get("noul", 0.0)
    is_continuation_noul = answers.get("is_continuation", {}).get("noul", 0.0)
    ambiguity = answers.get("ambiguity_score", {}).get("score", 0.0)
    ambiguity_conf = answers.get("ambiguity_score", {}).get("confidence", 0.0)

    suggested = answers.get("suggested_action", {}).get("choice", "none")
    suggested_conf = answers.get("suggested_action", {}).get("confidence", 0.0)
    latency_ms = answers.get("_latency_ms", 0.0)

    # Machine-native Jev semantic continuation detection (threshold >= 0.60 or affirmative fallback)
    is_continuation = (is_continuation_noul >= 0.60) or is_affirmative_continuation(user_prompt)
    is_bare = is_bare_link(user_prompt)
    is_info = is_informational_question(user_prompt)

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

    # 3. High Ambiguity & Bare URL Handling (skipped when Jev confirms continuation or informational queries)
    if not is_continuation and not is_info:
        if is_bare:
            sections.append(
                "> [!IMPORTANT]\n"
                f"> **Speculative Arbiter Advisory**: Detected bare URL without developer instructions (Score={ambiguity:.1f}/2.0, Conf={ambiguity_conf:.2f}).\n\n"
                f"[CRITICAL AGENT INSTRUCTION: The user provided a bare URL without instructions ('{user_prompt}'). "
                "DO NOT speculate on the intended action or browse random files. "
                "You MUST immediately invoke your `ask_question` tool to render an interactive clarification modal asking the user "
                "how they would like to proceed with this link (e.g., summarize content, extract submission/open-call details, integrate into code, or save to notes). "
                "DO NOT call any other tools (no run_command, no grep_search, no view_file).]"
            )
            actions_taken.append(f"bare_link_alert (Score={ambiguity:.1f})")
        elif ambiguity >= 1.85 and ambiguity_conf >= 0.80:
            sections.append(
                "> [!IMPORTANT]\n"
                f"> **Speculative Arbiter Advisory**: This user prompt was evaluated as open-ended or underspecified "
                f"(Score={ambiguity:.1f}/2.0, Conf={ambiguity_conf:.2f}).\n\n"
                f"[SPECULATIVE ARBITER ADVISORY: The user instruction '{user_prompt}' appears underspecified in isolation. "
                "If the preceding conversational context or current project state does NOT clearly identify the intended target, "
                "PREFER invoking `ask_question` to render an interactive clarification modal rather than wandering into unguided exploration. "
                "However, if the immediate prior conversation context already defines the target or action, proceed with standard intelligent execution.]"
            )
            actions_taken.append(f"ambiguity_alert (Score={ambiguity:.1f})")

    # 4. Log to SQLite Database for Active Learning & Continuous Calibration
    try:
        import safety_db
        if is_continuation:
            safety_db.record_speculative_feedback(conversation_id, user_prompt, "accepted_affirmative")
        safety_db.log_speculative_decision(
            conversation_id=conversation_id,
            prompt=user_prompt,
            latency_ms=latency_ms,
            needs_git=needs_git,
            needs_test=needs_test,
            ambiguity_score=ambiguity,
            ambiguity_conf=ambiguity_conf,
            suggested_action=suggested,
            suggested_conf=suggested_conf,
            actions_taken=actions_taken,
            is_continuation=is_continuation_noul
        )
    except Exception:
        pass

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

    full_message = f"<system_preflight_hook name='jev_speculative_arbiter'>\n{badge}\n\n{agent_directive}" + "\n\n".join(sections) + "\n</system_preflight_hook>"
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

    # 1. Turn-1 Guard: Speculative Pre-Flight only runs on initial invocation of user turn
    if context.get("invocationNum", 1) > 1:
        sys.exit(0)

    # 2. Debounce: Prevent duplicate execution if workspace and global hooks.json both fire
    conv_id = context.get("conversationId", "")
    inv_num = context.get("invocationNum", 1)
    lock_file = Path(os.path.expanduser("~/.gemini/config/.speculative_debounce.json"))
    now = time.time()
    try:
        if lock_file.exists():
            data = json.loads(lock_file.read_text(encoding="utf-8"))
            if data.get("conv_id") == conv_id and data.get("inv_num") == inv_num and (now - data.get("ts", 0)) < 2.5:
                sys.exit(0)
    except Exception:
        pass
    try:
        lock_file.write_text(json.dumps({"conv_id": conv_id, "inv_num": inv_num, "ts": now}), encoding="utf-8")
    except Exception:
        pass

    user_prompt = context.get("prompt", "")
    workspace_paths = context.get("workspacePaths", [])
    cwd = workspace_paths[0] if workspace_paths else os.getcwd()

    active_doc = ""
    open_docs = []
    prior_turn = ""

    if "transcriptPath" in context:
        t_info = extract_context_from_transcript(Path(context["transcriptPath"]))
        if not user_prompt:
            user_prompt = t_info.get("current_prompt", "")
        active_doc = t_info.get("active_document", "")
        open_docs = t_info.get("open_documents", [])
        prior_turn = t_info.get("prior_prompt", "")

    if not user_prompt:
        sys.exit(0)

    conversation_id = context.get("conversationId", "")

    try:
        answers = evaluate_speculative_batch(
            user_prompt=user_prompt,
            cwd=cwd,
            context=context,
            prior_turn=prior_turn,
            active_doc=active_doc,
            open_docs=open_docs
        )
        result = arbitrate_and_assemble(
            answers=answers,
            user_prompt=user_prompt,
            cwd=cwd,
            conversation_id=conversation_id,
            active_doc=active_doc,
            prior_turn=prior_turn
        )
        if result:
            print(json.dumps(result))
    except Exception:
        # Failsafe: exit 0 cleanly on network or parsing error
        sys.exit(0)


if __name__ == "__main__":
    main()
