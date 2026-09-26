"""Canonical skill catalog and shared progressive disclosure."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from jev.contracts import ContextItem, Outcome, Result
from jev.services.client import DecisionClient


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    path: Path
    body: str


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    result: dict[str, str] = {}
    current = ""
    for line in parts[1].splitlines():
        if re.match(r"^[A-Za-z_-]+\s*:", line):
            key, value = line.split(":", 1)
            current = key.strip()
            result[current] = value.strip().strip("'\"")
        elif current and line.startswith((" ", "\t")):
            result[current] = f"{result[current]} {line.strip()}".strip()
    return result


def load_catalog(roots: tuple[Path, ...]) -> list[Skill]:
    catalog: list[Skill] = []
    seen: set[tuple[str, Path]] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.glob("*/SKILL.md")):
            try:
                body = path.read_text(encoding="utf-8")
            except OSError:
                continue
            meta = _frontmatter(body)
            name = meta.get("name") or path.parent.name
            key = (name, path.resolve())
            if key in seen:
                continue
            seen.add(key)
            catalog.append(Skill(name, meta.get("description", ""), path.resolve(), body))
    return catalog


def _keyword_candidate(prompt: str, catalog: list[Skill]) -> tuple[Skill | None, float]:
    words = set(re.findall(r"[a-z0-9]+", prompt.lower()))
    best: Skill | None = None
    best_score = 0.0
    for skill in catalog:
        terms = set(re.findall(r"[a-z0-9]+", f"{skill.name} {skill.description}".lower()))
        useful = {word for word in words if len(word) >= 4}
        score = len(useful & terms) / max(1, min(len(useful), 6))
        if score > best_score:
            best, best_score = skill, score
    return best, min(best_score, 0.69)


def suggest(
    prompt: str,
    roots: tuple[Path, ...],
    client: DecisionClient | None,
    timeout: float,
    inject_body: bool = True,
) -> Result:
    started = time.monotonic()
    catalog = load_catalog(roots)
    if not prompt or not catalog:
        return Result(feature="skills", feature_version="1")
    selected, confidence = _keyword_candidate(prompt, catalog)
    requires_skill = confidence
    if client is not None:
        try:
            options = {skill.name: skill.description[:300] for skill in catalog[:255]}
            answers = client.evaluate(
                {"request": prompt},
                {
                    "skill": {
                        "type": "choice",
                        "instructions": "Select the single skill that best matches the request. Select none when no specialist workflow is needed.",
                        "criteria": {"none": "No listed skill is needed", **options},
                    },
                    "requires_skill": {
                        "type": "noul",
                        "instructions": "Would specialist workflow instructions materially improve this task?",
                    },
                },
                timeout,
            )
            answer = answers.get("skill", {})
            choice = answer.get("choice") or answer.get("selected")
            confidence = float(answer.get("confidence", 0.0))
            requires_skill = float(answers.get("requires_skill", {}).get("noul", 0.0))
            selected = next((skill for skill in catalog if skill.name == choice), None)
        except Exception:
            pass
    result = Result(
        outcome=Outcome.ABSTAIN,
        feature="skills",
        feature_version="1",
        data={"selected": selected.name if selected else "", "confidence": confidence},
        duration_ms=(time.monotonic() - started) * 1000,
    )
    if selected and confidence >= 0.80 and requires_skill >= 0.30 and inject_body:
        result.context.append(ContextItem("skills", selected.body, 80))
    elif selected and confidence >= 0.50 and requires_skill >= 0.30 and inject_body:
        result.context.append(
            ContextItem(
                "skills",
                f"Skill `{selected.name}` may apply (confidence {confidence:.2f}). Read {selected.path} if its workflow is needed.",
                40,
            )
        )
    return result


def list_skills(roots: tuple[Path, ...]) -> list[dict[str, str]]:
    return [
        {"name": skill.name, "description": skill.description, "path": str(skill.path)}
        for skill in load_catalog(roots)
    ]
