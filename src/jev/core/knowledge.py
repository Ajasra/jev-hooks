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


def learn(summary: str, details: str, root: Path) -> dict[str, Any]:
    """Explicitly create a knowledge item; never called as background work."""
    root.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
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
    return {"success": True, "id": directory.name, "path": str(directory.resolve())}


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
