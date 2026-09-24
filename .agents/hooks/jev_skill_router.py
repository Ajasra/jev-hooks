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


def load_skill_catalog():
    """Discovers all SKILL.md files in workspace and global directories."""
    skills = []
    roots = [
        Path(".agents/skills"),
        Path(os.path.expanduser("~/.gemini/config/skills"))
    ]
    for root in roots:
        if root.exists():
            for skill_dir in root.iterdir():
                skill_md = skill_dir / "SKILL.md"
                if skill_md.is_file():
                    content = skill_md.read_text(encoding="utf-8", errors="ignore")
                    skills.append({
                        "name": skill_dir.name,
                        "path": str(skill_md),
                        "snippet": content[:500]
                    })
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

    user_prompt = context.get("prompt", "")
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

    try:
        req = urllib.request.Request(
            ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            headers=BASE_HEADERS,
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=0.8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            
        answers = data.get("answers", {})
        requires_skill = answers.get("requires_skill", {}).get("noul", 0.0)
        selected = answers.get("selected_skill", {}).get("choice")
        confidence = answers.get("selected_skill", {}).get("confidence", 0.0)

        if requires_skill >= 0.65 and confidence >= 0.70 and selected:
            # Inject ephemeral skill instructions into context
            target = next((s for s in skills if s["name"] == selected), None)
            if target:
                full_body = Path(target["path"]).read_text(encoding="utf-8", errors="ignore")
                output = {
                    "injectSteps": [
                        {
                            "type": "ephemeralMessage",
                            "content": f"<activated_skill name='{selected}'>\n{full_body}\n</activated_skill>"
                        }
                    ]
                }
                print(json.dumps(output))
    except Exception:
        # Fail safe: allow normal turn execution without skill modification
        sys.exit(0)

if __name__ == "__main__":
    main()
