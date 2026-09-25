#!/usr/bin/env python3
"""
Jev Dual-Engine Knowledge Item (KI) Lifecycle Manager.
Implements Proposal C:
  --read    PreInvocation semantic triage & Turn-1 auto-mounting over <appDataDir>/knowledge/
  --distill Post-commit / session knowledge distiller and structured artifact synthesizer
  --learn   Explicit pattern capture from developer instruction or recent commit
  --list    Inspect and display active Knowledge Item catalog
"""

import sys
import os
import json
import time
import argparse
import urllib.request
from pathlib import Path

# Load shared Jev client config
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import env_loader
    API_KEY, ENDPOINT, MODEL, BASE_HEADERS = env_loader.get_client_config()
except ImportError:
    API_KEY = os.environ.get("TYPESAFE_API_KEY", "") or os.environ.get("OPENROUTER_API_KEY", "")
    ENDPOINT = os.environ.get("TYPESAFE_ENDPOINT", "https://api.typesafe.ai/v1/systemone")
    MODEL = os.environ.get("JEV_MODEL", "jev-latest")
    BASE_HEADERS = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}


def get_global_knowledge_dir() -> Path:
    """Resolves cross-platform Antigravity knowledge store path."""
    app_data = Path(os.environ.get("APPDATA", "~/.gemini")).expanduser()
    if (app_data / "antigravity-ide" / "knowledge").exists():
        return app_data / "antigravity-ide" / "knowledge"
    home_path = Path.home() / ".gemini" / "antigravity-ide" / "knowledge"
    home_path.mkdir(parents=True, exist_ok=True)
    return home_path


def get_workspace_knowledge_dir(cwd: str = None) -> Path:
    """Returns workspace-specific .agents/knowledge directory."""
    root = Path(cwd) if cwd else Path.cwd()
    target = root / ".agents" / "knowledge"
    return target


def call_jev(payload: dict, timeout: float = 4.0) -> dict:
    """Invokes Jev System One endpoint with graceful timeout and error handling."""
    if not API_KEY:
        return {}
    try:
        req = urllib.request.Request(
            ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            headers=BASE_HEADERS,
            method="POST"
        )
        start_time = time.time()
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        answers = data.get("answers", {})
        answers["_latency_ms"] = (time.time() - start_time) * 1000
        return answers
    except Exception as e:
        if "env_loader" in sys.modules:
            env_loader.log_debug("jev_ki_engine", f"Jev call failed: {e}")
        return {}


def load_installed_kis(cwd: str = None, include_global: bool = False) -> list:
    """
    Discovers all metadata.json entries from workspace-first knowledge roots.
    Workspace isolation is enforced by default to prevent cross-project contamination.
    """
    roots = []
    ws_dir = get_workspace_knowledge_dir(cwd)
    if ws_dir.exists():
        roots.append(ws_dir)

    if include_global:
        global_dir = get_global_knowledge_dir()
        if global_dir.exists() and global_dir not in roots:
            roots.append(global_dir)

    items = []
    seen = set()

    for root in roots:
        if not root.exists():
            continue
        for meta_file in root.glob("*/metadata.json"):
            try:
                data = json.loads(meta_file.read_text(encoding="utf-8"))
                ki_id = data.get("id", meta_file.parent.name)
                if ki_id not in seen:
                    seen.add(ki_id)
                    data["_dir"] = str(meta_file.parent)
                    data["_is_workspace"] = (root == ws_dir)
                    items.append(data)
            except Exception:
                continue
    return items


def run_read_triage(user_prompt: str, active_doc: str = "", cwd: str = None, include_global: bool = False) -> dict:
    """
    Read Engine: PreInvocation triage in ~70ms.
    Evaluates developer intent against catalog with 3-tier progressive disclosure:
    1. High Confidence (>= 0.70): Auto-mounts artifact into Turn 1 context.
    2. Borderline (0.40 <= P < 0.70): Injects clickable 1-line soft hint.
    3. Definite Non-Match (< 0.40): Injects Clean Assert to suppress hesitation.
    """
    ki_items = load_installed_kis(cwd, include_global=include_global)
    if not ki_items:
        # Zero KIs exist -> Exit in < 1ms
        return {}

    criteria = {item["id"]: f"{item.get('title', item['id'])}: {item.get('summary', '')}" for item in ki_items}
    criteria["none"] = "None of the existing Knowledge Items apply to this task"

    doc_context = f"Active Document: {active_doc}\n" if active_doc else ""
    payload = {
        "model": MODEL,
        "state": f"{doc_context}Developer Prompt:\n{user_prompt}",
        "questions": {
            "matching_ki": {
                "type": "choice",
                "instructions": "Which Knowledge Item describes architecture, precedents, or gotchas directly relevant to the user request?",
                "criteria": criteria
            },
            "has_relevant_ki": {
                "type": "noul",
                "instructions": "Does any existing Knowledge Item directly apply to the code or architecture the user is asking about?"
            }
        }
    }

    answers = call_jev(payload)
    if not answers:
        return {}

    has_rel = answers.get("has_relevant_ki", {}).get("noul", 0.0)
    choice = answers.get("matching_ki", {}).get("choice", "none")
    conf = answers.get("matching_ki", {}).get("confidence", 0.0)

    # 1. Tier 1: High Confidence -> Auto-Mount Artifact (saves turn-1 tool exploration)
    if has_rel >= 0.70 and choice != "none" and conf >= 0.70:
        matched_item = next((item for item in ki_items if item["id"] == choice), None)
        if matched_item:
            target_dir = Path(matched_item["_dir"]) / "artifacts"
            artifact_text = ""
            for art in target_dir.glob("*.md"):
                try:
                    artifact_text = art.read_text(encoding="utf-8")
                    break
                except Exception:
                    continue

            if artifact_text:
                return {
                    "injectSteps": [
                        {
                            "ephemeralMessage": (
                                f"<system_preflight_hook name='jev_ki_engine'>\n"
                                f"> **Jev KI Pre-Flight**: Auto-mounted relevant architectural precedent `{choice}` (Conf: {conf:.2f}).\n\n"
                                f"<ki_context id='{choice}'>\n"
                                f"{artifact_text}\n"
                                f"</ki_context>\n"
                                f"</system_preflight_hook>"
                            )
                        }
                    ]
                }

    # 2. Tier 2: Borderline -> Compact 1-line soft hint with link
    elif has_rel >= 0.40 and choice != "none" and conf >= 0.40:
        matched_item = next((item for item in ki_items if item["id"] == choice), None)
        if matched_item:
            ki_dir = matched_item["_dir"]
            file_link = f"file:///{Path(ki_dir).as_posix()}"
            title = matched_item.get("title", choice)
            return {
                "injectSteps": [
                    {
                        "ephemeralMessage": (
                            f"<system_preflight_hook name='jev_ki_engine'>\n"
                            f"> [!TIP]\n"
                            f"> **Jev KI Hint**: Knowledge Item `{choice}` ({title}) may be relevant (Conf: {conf:.2f}). "
                            f"Inspect if needed at [{choice}]({file_link}).\n"
                            f"</system_preflight_hook>"
                        )
                    }
                ]
            }

    # 3. Tier 3: Definite Non-Match -> Clean Assert
    elif has_rel < 0.40:
        return {
            "injectSteps": [
                {
                    "ephemeralMessage": (
                        "<system_preflight_hook name='jev_ki_engine'>\n"
                        "> **Jev KI Pre-Flight**: Automated check confirmed no repository Knowledge Items apply. "
                        "Proceed directly to fresh investigation without searching KIs.\n"
                        "</system_preflight_hook>"
                    )
                }
            ]
        }

    return {}


def run_write_distillation(
    session_summary: str,
    git_diff: str,
    references: list = None,
    cwd: str = None,
    force_write: bool = False,
    target_store: str = "workspace"
) -> dict:
    """
    Write Engine: Autonomous Knowledge Distillation.
    Evaluates completed work, performs deduplication, and formats structured patterns.
    """
    existing_kis = load_installed_kis(cwd)
    ki_criteria = {ki["id"]: f"{ki.get('title', ki['id'])}: {ki.get('summary', '')}" for ki in existing_kis}
    ki_criteria["none_new_topic"] = "This is a completely new architectural domain or unrelated topic"

    payload = {
        "model": MODEL,
        "state": f"Summary of Resolved Work:\n{session_summary}\n\nDiff:\n{git_diff[:3000]}",
        "questions": {
            "is_reusable_pattern": {
                "type": "noul",
                "instructions": (
                    "Does this work establish an important reusable architectural pattern, critical gotcha, "
                    "or convention that future coding agents must follow?"
                )
            },
            "novelty_score": {
                "type": "score",
                "instructions": "Rate how unique and non-obvious this architectural knowledge is.",
                "criteria": [
                    "Routine code edit easily inferred from standard language documentation",
                    "Helpful project configuration trick or convention",
                    "Critical non-obvious architectural pattern, invariant, or security gotcha"
                ]
            },
            "architectural_domain": {
                "type": "choice",
                "instructions": "What primary engineering domain does this knowledge belong to?",
                "criteria": {
                    "auth_security": "Authentication, authorization, tokens, secrets, encryption",
                    "database_migrations": "Schema migrations, ORM gotchas, connection pooling",
                    "build_pipeline": "Build tooling, bundlers, CI/CD scripts, package resolution",
                    "concurrency_state": "State machines, async handling, lifecycle hooks, race conditions",
                    "tool_harness": "Agent hooks, linters, safety gates, subagent orchestration",
                    "testing_fixtures": "Mocking, integration test setup, test database harnesses",
                    "general": "General architectural patterns or domain models"
                }
            },
            "existing_ki_to_update": {
                "type": "choice",
                "instructions": "Does this work update, refine, or obsolete an existing Knowledge Item?",
                "criteria": ki_criteria
            }
        }
    }

    answers = call_jev(payload)
    if not answers and not force_write:
        return {"success": False, "reason": "Jev evaluation failed"}

    is_reusable = answers.get("is_reusable_pattern", {}).get("noul", 1.0 if force_write else 0.0)
    novelty = answers.get("novelty_score", {}).get("score", 2.0 if force_write else 0.0)
    domain = answers.get("architectural_domain", {}).get("choice", "general")
    target_ki = answers.get("existing_ki_to_update", {}).get("choice", "none_new_topic")
    target_conf = answers.get("existing_ki_to_update", {}).get("confidence", 0.0)

    if (is_reusable >= 0.75 and novelty >= 1.5) or force_write:
        # Resolve target directory (Workspace vs Global)
        if target_store == "workspace":
            base_root = get_workspace_knowledge_dir(cwd)
        else:
            base_root = get_global_knowledge_dir()

        base_root.mkdir(parents=True, exist_ok=True)

        # Deduplication check
        if target_ki != "none_new_topic" and target_conf >= 0.75:
            matched_item = next((k for k in existing_kis if k["id"] == target_ki), None)
            ki_id = target_ki
            ki_dir = Path(matched_item["_dir"]) if matched_item else base_root / ki_id
            is_update = True
        else:
            timestamp_str = time.strftime("%Y%m%d_%H%M%S")
            ki_id = f"ki_{timestamp_str}_{domain}"
            ki_dir = base_root / ki_id
            is_update = False

        artifacts_dir = ki_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        title = session_summary.splitlines()[0][:80].strip("# ")
        if not title:
            title = f"Architectural Convention for {domain}"

        meta = {
            "id": ki_id,
            "title": title,
            "domain": domain,
            "summary": session_summary[:250],
            "novelty": novelty,
            "reusability": is_reusable,
            "updated_at" if is_update else "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "references": references or []
        }
        (ki_dir / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

        # Format 3-part structured pattern
        artifact_content = (
            f"# {title}\n\n"
            f"**Domain**: `{domain}` | **Confidence**: {target_conf:.2f} | **Updated**: {meta.get('updated_at', meta.get('created_at'))}\n\n"
            f"## 1. Problem Context & Architectural Invariant\n"
            f"{session_summary}\n\n"
            f"## 2. Canonical Solution & Implementation Diff\n"
            f"```diff\n{git_diff[:2500]}\n```\n"
        )
        (artifacts_dir / "architectural_pattern.md").write_text(artifact_content, encoding="utf-8")

        return {
            "success": True,
            "id": ki_id,
            "is_update": is_update,
            "path": str(ki_dir),
            "novelty": novelty,
            "reusability": is_reusable
        }

    return {
        "success": False,
        "reason": f"Did not meet novelty threshold (reusable: {is_reusable:.2f}, novelty: {novelty:.2f})"
    }


def capture_git_diff(cwd: str = None) -> tuple:
    """Extracts recent git diff and log summary for automatic distillation."""
    import subprocess
    root = cwd or str(Path.cwd())
    try:
        # Check staged diff first, then HEAD~1..HEAD, then unstaged
        proc_log = subprocess.run(
            ["cmd", "/c", "git log -1 --pretty=format:%B"],
            cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        summary = (proc_log.stdout or "").strip() or "Recent repository update"

        proc_diff = subprocess.run(
            ["cmd", "/c", "git diff HEAD~1..HEAD -U2"],
            cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        diff = (proc_diff.stdout or "").strip()

        if not diff:
            proc_diff2 = subprocess.run(
                ["cmd", "/c", "git diff -U2"],
                cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace"
            )
            diff = (proc_diff2.stdout or "").strip()

        return summary, diff
    except Exception as e:
        return "Manual capture", f"Unable to extract diff: {e}"


def main():
    parser = argparse.ArgumentParser(description="Jev Dual-Engine Knowledge Item Lifecycle Manager")
    parser.add_argument("--read", action="store_true", help="Run PreInvocation triage from stdin")
    parser.add_argument("--distill", action="store_true", help="Run distillation from git diff or stdin")
    parser.add_argument("--learn", action="store_true", help="Explicitly capture a pattern into a KI")
    parser.add_argument("--list", action="store_true", help="List installed Knowledge Items")
    parser.add_argument("--title", type=str, default="", help="Title for manual learn capture")
    parser.add_argument("--summary", type=str, default="", help="Summary of the pattern")
    parser.add_argument("--domain", type=str, default="tool_harness", help="Architectural domain")
    parser.add_argument("--force", action="store_true", help="Bypass novelty gate on explicit learn")
    parser.add_argument("--store", type=str, default="workspace", choices=["workspace", "global"], help="Target store (default: workspace)")
    parser.add_argument("--include-global", action="store_true", help="Include global knowledge items in triage/listing")
    parser.add_argument("--cwd", type=str, default="", help="Working directory context")

    args = parser.parse_args()
    cwd = args.cwd or str(Path.cwd())

    if args.list:
        kis = load_installed_kis(cwd, include_global=args.include_global)
        print(f"\nInstalled Knowledge Items ({len(kis)} found):")
        print(f"{'ID':<30} {'Domain':<18} {'Scope':<10} {'Title'}")
        print("-" * 80)
        for k in kis:
            scope = "Workspace" if k.get("_is_workspace") else "Global"
            print(f"{k.get('id', ''):<30} {k.get('domain', 'general'):<18} {scope:<10} {k.get('title', '')[:35]}")
        sys.exit(0)

    if args.read:
        raw = sys.stdin.read()
        try:
            context = json.loads(raw) if raw.strip() else {}
        except Exception:
            context = {}
        prompt = context.get("prompt", "")
        active_doc = context.get("activeDocument", "")
        result = run_read_triage(prompt, active_doc, cwd, include_global=args.include_global)
        print(json.dumps(result))
        sys.exit(0)

    if args.distill:
        # Check if diff is piped
        piped = ""
        if not sys.stdin.isatty():
            piped = sys.stdin.read().strip()

        if piped:
            summary = args.summary or "Piped Knowledge Distillation"
            diff = piped
        else:
            summary, diff = capture_git_diff(cwd)

        res = run_write_distillation(summary, diff, cwd=cwd, force_write=args.force, target_store=args.store)
        print(json.dumps(res, indent=2))
        sys.exit(0)

    if args.learn:
        summary, diff = capture_git_diff(cwd)
        if args.summary:
            summary = f"{args.title}\n{args.summary}" if args.title else args.summary
        res = run_write_distillation(summary, diff, cwd=cwd, force_write=True, target_store=args.store)
        print(json.dumps(res, indent=2))
        sys.exit(0)

    parser.print_help()


if __name__ == "__main__":
    main()
