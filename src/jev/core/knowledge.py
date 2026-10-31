"""Shared knowledge-item discovery and explicit learning."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jev.contracts import ContextItem, Outcome, Result
from jev.services.client import DecisionClient, failure_details


def parse_gotcha_file(path: Path) -> dict[str, Any] | None:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not content.strip():
        return None

    title_match = re.search(r"^#\s+(?:Gotcha:\s*)?(.+)$", content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else path.stem.replace("_", " ")

    tags_match = re.search(r"-\s+\*\*Tags\*\*:\s*\[?(.*?)\]?$", content, re.MULTILINE)
    tags = [t.strip().strip("'\"") for t in tags_match.group(1).split(",")] if tags_match else []

    trap_match = re.search(r"-\s+\*\*Trap\*\*:\s*(.+?)(?=\n-\s+\*\*|\Z)", content, re.DOTALL | re.MULTILINE)
    trap = trap_match.group(1).strip() if trap_match else ""

    rem_match = re.search(r"-\s+\*\*Remediation\*\*:\s*(.+?)(?=\n-\s+\*\*|\Z)", content, re.DOTALL | re.MULTILINE)
    remediation = rem_match.group(1).strip() if rem_match else ""

    summary = trap or content[:300]
    return {
        "id": f"gotcha_{path.stem}",
        "title": title,
        "summary": summary,
        "tags": tags,
        "trap": trap,
        "remediation": remediation,
        "provenance": "gotcha",
        "_dir": str(path.parent.resolve()),
        "_artifact": str(path.resolve()),
    }


def load_items(roots: tuple[Path, ...]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for root in roots:
        if not root.exists():
            continue
        for metadata in sorted(root.glob("*/metadata.json")):
            try:
                item = json.loads(metadata.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            item["_dir"] = str(metadata.parent.resolve())
            artifact = metadata.parent / "artifacts" / "architectural_pattern.md"
            if artifact.exists():
                item["_artifact"] = str(artifact.resolve())
            items.append(item)
        for md_file in sorted(root.glob("*.md")):
            gotcha = parse_gotcha_file(md_file)
            if gotcha:
                items.append(gotcha)
    return items


def _keyword_match(prompt: str, items: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, float]:
    prompt_terms = set(re.findall(r"[a-z0-9]+", prompt.lower()))
    best: dict[str, Any] | None = None
    best_score = 0.0
    for item in items:
        haystack = " ".join(str(item.get(key, "")) for key in ("id", "title", "summary", "tags", "trap", "remediation"))
        terms = set(re.findall(r"[a-z0-9]+", haystack.lower()))
        score = len({term for term in prompt_terms if len(term) >= 4} & terms) / max(1, min(len(prompt_terms), 8))
        if score > best_score:
            best, best_score = item, score
    return best, min(best_score, 0.69)


def search(
    prompt: str,
    roots: tuple[Path, ...],
    client: DecisionClient | None = None,
    timeout: float = 0.25,
) -> Result:
    started = time.monotonic()
    provider_error = ""
    provider_data = {"provider_status": "not_configured" if client is None else "not_called"}
    items = load_items(roots)
    if not prompt or not items:
        return Result(feature="knowledge", feature_version="1",
                      reason_code="missing_prompt" if not prompt else "empty_catalog",
                      data={"catalog_count": len(items), "provider_status": "not_called"},
                      duration_ms=(time.monotonic() - started) * 1000)
    selected, confidence = _keyword_match(prompt, items)
    if client is not None:
        try:
            criteria = {str(item.get("id", index)): str(item.get("summary") or item.get("title") or "")[:300]
                        for index, item in enumerate(items[:254])}
            answers = client.evaluate(
                {"request": prompt},
                {"knowledge": {"type": "choice", "instructions": "Select the relevant knowledge item, or none.",
                               "criteria": {"none": "No item is relevant", **criteria}}},
                timeout,
            )
            answer = answers.get("knowledge", {})
            choice = answer.get("choice") or answer.get("selected")
            confidence = float(answer.get("confidence", 0.0))
            selected = next((item for item in items if str(item.get("id")) == str(choice)), None)
            provider_data = {"provider_status": "ok"}
        except Exception as exc:
            provider_error = type(exc).__name__
            provider_data = failure_details(exc)
    result = Result(
        outcome=Outcome.ABSTAIN,
        error=provider_error,
        timed_out=bool(provider_data.get("timed_out")),
        feature="knowledge",
        feature_version="1",
        data={**provider_data, "catalog_count": len(items), "selected": selected.get("id", "") if selected else "", "confidence": confidence},
        duration_ms=(time.monotonic() - started) * 1000,
    )
    if selected and confidence >= 0.50:
        artifact_path = Path(selected.get("_artifact", ""))
        if selected.get("provenance") == "gotcha":
            trap_text = f"\nTrap: {selected.get('trap')}" if selected.get('trap') else ""
            rem_text = f"\nRemediation: {selected.get('remediation')}" if selected.get('remediation') else ""
            gotcha_text = f"Operational Gotcha [{selected.get('title')}]:{trap_text}{rem_text}"
            result.context.append(ContextItem("knowledge", gotcha_text, 70))
        elif confidence >= 0.80 and artifact_path.is_file():
            text = artifact_path.read_text(encoding="utf-8", errors="replace")
            result.context.append(ContextItem("knowledge", text, 70))
        else:
            result.context.append(ContextItem(
                "knowledge",
                f"Knowledge item `{selected.get('id', '')}` may apply: {selected.get('title', '')}. Source: {selected.get('_dir', '')}",
                35,
            ))
    return result


def learn(
    summary: str,
    details: str,
    root: Path,
    client: DecisionClient | None = None,
    timeout: float = 0.50,
) -> dict[str, Any]:
    """Save or update a knowledge item with Jev deduplication (RFC-03)."""
    root.mkdir(parents=True, exist_ok=True)
    existing_items = load_items((root,))

    matched_item: dict[str, Any] | None = None
    target_ki = "none_new_topic"
    target_conf = 0.0

    if client is not None and existing_items:
        try:
            ki_criteria = {
                str(item.get("id")): f"{item.get('title')}: {item.get('summary', '')[:180]}"
                for item in existing_items[:254]
            }
            ki_criteria["none_new_topic"] = "This is a completely new architectural domain or unrelated topic"

            answers = client.evaluate(
                {"summary": summary, "details": details[:2500]},
                {
                    "existing_ki_to_update": {
                        "type": "choice",
                        "instructions": "Does this work update, refine, or obsolete an existing Knowledge Item?",
                        "criteria": ki_criteria,
                    }
                },
                timeout,
            )
            answer = answers.get("existing_ki_to_update", {})
            choice = str(answer.get("choice") or answer.get("selected") or "none_new_topic")
            target_conf = float(answer.get("confidence", 0.0))
            if choice != "none_new_topic" and target_conf >= 0.75:
                matched_item = next((k for k in existing_items if str(k.get("id")) == choice), None)
                if matched_item:
                    target_ki = choice
        except Exception:
            matched_item = None

    now = datetime.now(timezone.utc)
    is_update = matched_item is not None

    if is_update and matched_item:
        ki_id = target_ki
        directory = Path(matched_item["_dir"])
        artifacts = directory / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)

        meta_path = directory / "metadata.json"
        meta: dict[str, Any] = {}
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                meta = {}
        meta["id"] = ki_id
        meta["updated_at"] = now.isoformat()
        if summary.strip():
            meta["summary"] = summary[:500]
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        pattern_file = artifacts / "architectural_pattern.md"
        existing_content = pattern_file.read_text(encoding="utf-8", errors="replace") if pattern_file.is_file() else ""
        addition = (
            f"\n\n---\n### Update: {now.strftime('%Y-%m-%d %H:%M:%SZ')}\n"
            f"{summary}\n\n#### Additional Evidence\n{details}\n"
        )
        pattern_file.write_text((existing_content + addition).strip() + "\n", encoding="utf-8")

        return {
            "success": True,
            "id": ki_id,
            "is_update": True,
            "confidence": target_conf,
            "path": str(directory.resolve()),
        }

    slug = re.sub(r"[^a-z0-9]+", "_", summary.lower()).strip("_")[:40] or "knowledge"
    item_id = f"ki_{now.strftime('%Y%m%d_%H%M%S')}_{slug}"
    directory = root / item_id
    suffix = 1
    while directory.exists():
        directory = root / f"{item_id}_{suffix}"
        suffix += 1
    artifacts = directory / "artifacts"
    artifacts.mkdir(parents=True)
    metadata = {
        "id": directory.name,
        "title": summary.splitlines()[0][:120],
        "summary": summary[:500],
        "created_at": now.isoformat(),
        "provenance": "explicit",
    }
    (directory / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (artifacts / "architectural_pattern.md").write_text(
        f"# {metadata['title']}\n\n{summary}\n\n## Evidence\n\n{details}\n",
        encoding="utf-8",
    )
    return {
        "success": True,
        "id": directory.name,
        "is_update": False,
        "path": str(directory.resolve()),
    }


def propose_learning(
    context_text: str,
    harness: str,
    client: DecisionClient | None = None,
    timeout: float = 0.25,
) -> Result:
    """Evaluate whether recent work establishes a reusable pattern to propose learning."""
    started = time.monotonic()
    if not context_text.strip() or client is None:
        return Result(feature="knowledge_proposer", feature_version="1")

    try:
        answers = client.evaluate(
            {"context": context_text[:3500]},
            {
                "is_reusable_pattern": {
                    "type": "noul",
                    "instructions": (
                        "Does this completed work, error resolution, or commit establish a non-obvious "
                        "architectural convention, gotcha, or reusable design pattern that should be saved to knowledge?"
                    ),
                },
                "pattern_title": {
                    "type": "choice",
                    "instructions": "What domain best captures this pattern?",
                    "criteria": {
                        "architecture": "High-level architecture, module boundary, or harness protocol",
                        "security": "Authentication, authorization, tokens, secrets, or file permissions",
                        "build_test": "Build configuration, test fixtures, or runner idiosyncrasies",
                        "routine": "Routine application logic or trivial formatting detail",
                    },
                },
            },
            timeout,
        )
        is_reusable = float(answers.get("is_reusable_pattern", {}).get("noul", 0.0))
        domain = str(answers.get("pattern_title", {}).get("choice") or "")

        if is_reusable >= 0.75 and domain != "routine":
            if harness == "codex":
                # Option B for Codex: Visible systemMessage guiding the model to ask the user
                msg = (
                    "[Jev Knowledge Advisory]: A reusable architectural pattern was established in this step. "
                    "Ask the user in your response: 'Would you like me to save this solution to .agents/knowledge/ using knowledge_learn?'"
                )
            else:
                # Antigravity: direct instruction to present an interactive choice
                msg = (
                    "[Jev Knowledge Advisory]: A reusable architectural pattern was established in this step. "
                    "Propose saving it to repository knowledge using `knowledge_learn` or render an interactive modal."
                )
            return Result(
                outcome=Outcome.ABSTAIN,
                feature="knowledge_proposer",
                feature_version="1",
                context=[ContextItem("knowledge_proposer", msg, priority=65)],
                data={"is_reusable": is_reusable, "domain": domain},
                duration_ms=(time.monotonic() - started) * 1000,
            )
    except Exception:
        pass

    return Result(
        feature="knowledge_proposer",
        feature_version="1",
        duration_ms=(time.monotonic() - started) * 1000,
    )



def record_gotcha(
    title: str,
    trap: str,
    remediation: str,
    root: Path,
    tags: list[str] | str | None = None,
    slug: str | None = None,
) -> dict[str, Any]:
    """Persist an operational gotcha into repository docs/gotchas/."""
    root.mkdir(parents=True, exist_ok=True)
    if not slug:
        slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:50] or "gotcha"
    file_path = root / f"{slug}.md"

    if isinstance(tags, list):
        tags_str = ", ".join(tags)
    elif isinstance(tags, str):
        tags_str = tags
    else:
        tags_str = ""

    content = (
        f"# Gotcha: {title}\n"
        f"- **Tags**: [{tags_str}]\n"
        f"- **Trap**: {trap}\n"
        f"- **Remediation**: {remediation}\n"
    )
    file_path.write_text(content, encoding="utf-8")
    return {
        "success": True,
        "id": f"gotcha_{slug}",
        "title": title,
        "path": str(file_path.resolve()),
    }
