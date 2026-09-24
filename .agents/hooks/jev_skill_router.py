#!/usr/bin/env python3
"""
PreInvocation Hook: Jev Dynamic Skill Selection & Routing Engine for Antigravity.
Evaluates incoming user request against candidate SKILL.md frontmatter in ~100ms.
Injects ephemeral instructions only for qualifying skills (P >= 0.70).
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


def load_skill_catalog(workspace_paths=None):
    """Discovers all SKILL.md files in workspace, global directories, and plugins."""
    skills = []
    seen = set()

    skill_files = []
    # 1. Local workspace skills from CWD and reported workspace paths
    roots = [Path.cwd()]
    if workspace_paths:
        for wp in workspace_paths:
            p = Path(wp)
            if p.exists() and p not in roots:
                roots.append(p)

    for r in roots:
        skill_files.extend((r / ".agents" / "skills").glob("*/SKILL.md"))
        skill_files.extend((r / ".agents" / "plugins").glob("*/skills/*/SKILL.md"))

    # 2. Global user skills & plugins
    global_cfg = Path(os.path.expanduser("~/.gemini/config"))
    skill_files.extend((global_cfg / "skills").glob("*/SKILL.md"))
    skill_files.extend((global_cfg / "plugins").glob("*/skills/*/SKILL.md"))

    for skill_md in skill_files:
        try:
            resolved = skill_md.resolve()
            if resolved.is_file():
                name = resolved.parent.name
                if name not in seen:
                    seen.add(name)
                    content = resolved.read_text(encoding="utf-8", errors="ignore")
                    skills.append({
                        "name": name,
                        "path": str(resolved),
                        "snippet": content[:500]
                    })
        except Exception:
            continue
    return skills

def main():
    if not API_KEY:
        # Fallback if no API key is provided
        sys.exit(0)

    try:
        raw_input = sys.stdin.read()
        context = json.loads(raw_input) if raw_input.strip() else {}
    except Exception:
        sys.exit(0)

    workspace_paths = context.get("workspacePaths", [])
    skills = load_skill_catalog(workspace_paths)

    user_prompt = context.get("prompt", "")
    if not user_prompt and "transcriptPath" in context:
        try:
            t_path = Path(context["transcriptPath"])
            if t_path.exists():
                for line in reversed(t_path.read_text(encoding="utf-8", errors="ignore").splitlines()):
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

    skills = load_skill_catalog()
    if not skills or not user_prompt:
        sys.exit(0)

    # Build Jev Choice criteria
    criteria = {s["name"]: s["snippet"][:200] for s in skills}
    payload = {
        "model": MODEL,
        "state": user_prompt,
        "questions": {
            "selected_skill": {
                "type": "choice",
                "instructions": "Which specialized skill, if any, is required to execute this developer prompt?",
                "criteria": criteria
            },
            "requires_skill": {
                "type": "noul",
                "instructions": "Does this request genuinely require a documented procedure or specialized tool skill rather than standard general programming?"
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
            
        answers = data.get("answers", {})
        requires_skill = answers.get("requires_skill", {}).get("noul", 0.0)
        selected = answers.get("selected_skill", {}).get("choice")
        confidence = answers.get("selected_skill", {}).get("confidence", 0.0)
        latency_ms = (time.time() - start_time) * 1000

        should_activate = selected and (confidence >= 0.80 or (confidence >= 0.65 and requires_skill >= 0.40))
        if should_activate:
            # Inject ephemeral skill instructions into context
            target = next((s for s in skills if s["name"] == selected), None)
            if target:
                full_body = Path(target["path"]).read_text(encoding="utf-8", errors="ignore")

                # Log activation via env_loader (only if DEBUG=true)
                try:
                    env_loader.log_debug(
                        "skill_router",
                        f"Activated: '{selected}' (Confidence: {confidence:.2f}, Noul: {requires_skill:.2f}, Latency: {latency_ms:.0f}ms) | Prompt: {user_prompt[:70]}..."
                    )
                except Exception:
                    pass

                badge_notice = (
                    f"> **Activated Skill**: `{selected}`\n\n"
                    f"[INSTRUCTION FOR AGENT: The Jev Dynamic Router selected and activated '{selected}' for this turn. "
                    f"Start your response with the badge `> **Activated Skill**: {selected}` so the developer is informed.]\n\n"
                )

                output = {
                    "injectSteps": [
                        {
                            "ephemeralMessage": f"<activated_skill name='{selected}'>\n{badge_notice}{full_body}\n</activated_skill>"
                        }
                    ]
                }
                print(json.dumps(output))
        else:
            try:
                env_loader.log_debug(
                    "skill_router",
                    f"No skill activated (Candidate: '{selected}', Confidence: {confidence:.2f}, Noul: {requires_skill:.2f}, Latency: {latency_ms:.0f}ms) | Prompt: {user_prompt[:70]}..."
                )
            except Exception:
                pass
    except Exception:
        # Fail safe: allow normal turn execution without skill modification
        sys.exit(0)

if __name__ == "__main__":
    main()
