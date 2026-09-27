"""Semantic diff linting with KI-style rule discovery and calibrated advisories."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jev.services.client import DecisionClient
from jev.services.storage import Storage, redact

MODES = {"observe", "advisory", "ci_enforced"}
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


@dataclass(frozen=True)
class Rule:
    id: str
    version: int
    title: str
    question: str
    mode: str
    level: str
    review_threshold: float
    violation_threshold: float
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    digest: str


def load_rules(roots: tuple[Path, ...]) -> list[Rule]:
    rules: list[Rule] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.glob("*/metadata.json")):
            raw = json.loads(path.read_text(encoding="utf-8"))
            if str(raw.get("status", "active")) in {"disabled", "deprecated"}:
                continue
            rule_id = str(raw["id"])
            if rule_id in seen:
                raise ValueError(f"Duplicate semantic lint rule id: {rule_id}")
            mode = str(raw.get("mode", "observe"))
            level = str(raw.get("level", "warning"))
            review = float(raw.get("review_threshold", 0.60))
            violation = float(raw.get("violation_threshold", 0.82))
            if mode not in MODES or level not in {"warning", "error"} or not 0 <= review <= violation <= 1:
                raise ValueError(f"Invalid semantic lint rule: {rule_id}")
            canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"))
            rules.append(Rule(
                rule_id, int(raw.get("version", 1)), str(raw.get("title", rule_id)),
                str(raw["question"]), mode, level, review, violation,
                tuple(raw.get("include", ["**/*"])), tuple(raw.get("exclude", [])),
                hashlib.sha256(canonical.encode()).hexdigest(),
            ))
            seen.add(rule_id)
    return rules


def collect_diff(workspace: Path, *, staged: bool, base_ref: str | None, max_chars: int = 60_000) -> tuple[str, bool]:
    if staged and base_ref:
        raise ValueError("Choose either staged changes or a base reference")
    if base_ref:
        subprocess.run(["git", "rev-parse", "--verify", f"{base_ref}^{{commit}}"], cwd=workspace,
                       check=True, capture_output=True, text=True, timeout=5)
    command = ["git", "diff", "--unified=3", "--no-ext-diff", "--no-textconv"]
    if staged:
        command.append("--cached")
    elif base_ref:
        command.append(f"{base_ref}...HEAD")
    completed = subprocess.run(command, cwd=workspace, check=True, capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=10)
    return completed.stdout[:max_chars], len(completed.stdout) > max_chars


def _hunks(diff: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    path = ""
    start = end = 0
    lines: list[str] = []
    def flush() -> None:
        if path and lines:
            results.append({"path": path, "start": start, "end": end, "text": "\n".join(lines)[:12_000]})
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            flush(); lines = []; path = line[6:]; start = end = 0
        elif match := HUNK.match(line):
            flush(); lines = [line]; start = int(match.group(1)); end = start + max(int(match.group(2) or 1) - 1, 0)
        elif path and lines:
            lines.append(line)
    flush()
    return results[:50]


def _matches(path: str, pattern: str) -> bool:
    return fnmatch.fnmatch(path, pattern) or (pattern.startswith("**/") and fnmatch.fnmatch(path, pattern[3:]))


def evaluate(*, workspace: Path, roots: tuple[Path, ...], storage: Storage,
             client: DecisionClient | None, harness: str, workspace_id: str,
             staged: bool = True, base_ref: str | None = None, timeout: float = 0.25) -> dict[str, Any]:
    started = time.monotonic()
    rules = load_rules(roots)
    diff, truncated = collect_diff(workspace, staged=staged, base_ref=base_ref)
    diff_digest = hashlib.sha256(diff.encode()).hexdigest()
    if not diff:
        return {"status": "pass", "findings": [], "evaluated_rules": len(rules),
                "diff_digest": diff_digest, "truncated": truncated, "duration_ms": 0.0}
    if client is None:
        return {"status": "unavailable", "findings": [], "evaluated_rules": 0,
                "diff_digest": diff_digest, "truncated": truncated,
                "reason": "No TypeSafe or OpenRouter API key is configured.",
                "duration_ms": round((time.monotonic() - started) * 1000, 2)}
    findings: list[dict[str, Any]] = []
    for hunk in _hunks(diff):
        applicable = [rule for rule in rules if any(_matches(hunk["path"], pattern) for pattern in rule.include)
                      and not any(_matches(hunk["path"], pattern) for pattern in rule.exclude)]
        if not applicable:
            continue
        questions = {rule.id: {"type": "noul", "instructions": rule.question} for rule in applicable[:10]}
        try:
            answers = client.evaluate({"path": hunk["path"], "diff_hunk": redact(hunk["text"], 12_000)}, questions, timeout)
        except Exception as exc:  # noqa: BLE001 - optional provider failures become unavailable
            return {"status": "unavailable", "findings": findings, "evaluated_rules": len(rules),
                    "diff_digest": diff_digest, "truncated": truncated,
                    "reason": f"Semantic provider unavailable: {type(exc).__name__}",
                    "duration_ms": round((time.monotonic() - started) * 1000, 2)}
        for rule in applicable[:10]:
            answer = answers.get(rule.id, {})
            probability = float(answer.get("noul", answer.get("probability", 0.0))) if isinstance(answer, dict) else float(answer or 0.0)
            classification = "violation" if probability >= rule.violation_threshold else "review" if probability >= rule.review_threshold else "pass"
            decision = {
                "event_id": str(uuid.uuid4()), "harness": harness or "direct", "workspace_id": workspace_id,
                "rule_id": rule.id, "rule_version": rule.version, "rule_digest": rule.digest,
                "diff_digest": diff_digest, "path": hunk["path"], "hunk_start": hunk["start"], "hunk_end": hunk["end"],
                "probability": probability, "classification": classification, "mode": rule.mode,
                "duration_ms": (time.monotonic() - started) * 1000, "redacted": int("[REDACTED]" in redact(hunk["text"], 12_000)),
                "truncated": int(truncated),
            }
            decision_id = storage.record_semantic_lint_decision(decision)
            if classification != "pass" and rule.mode != "observe":
                presentation = "prompt_user" if harness == "antigravity" else "warn_user"
                findings.append({**decision, "decision_id": decision_id, "title": rule.title,
                                 "level": rule.level, "presentation": presentation,
                                 "message": f"Possible {rule.title} violation in {hunk['path']}:{hunk['start']}-{hunk['end']} (confidence {probability:.2f}). Review the rule and surrounding code."})
    status = "review" if findings else "pass"
    return {"status": status, "findings": findings, "evaluated_rules": len(rules), "diff_digest": diff_digest,
            "truncated": truncated, "duration_ms": round((time.monotonic() - started) * 1000, 2)}
