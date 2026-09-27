"""Universal output verification & citation checking (RFC-07)."""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from jev.contracts import ContextItem, Event, Harness, Operation, Outcome, Result
from jev.services.client import DecisionClient
from jev.services.paths import Settings
from jev.services.storage import Storage, redact

VERIFICATION_FEATURE = "verification"
VERIFICATION_VERSION = "1"

QUESTIONS = {
    "method_supported_by_docs": {
        "type": "noul",
        "instructions": (
            "Does the provided reference documentation or context confirm that the proposed API methods, "
            "functions, or symbols in the code snippet exist and are valid?"
        ),
    },
    "arguments_match_spec": {
        "type": "noul",
        "instructions": (
            "Are the arguments, parameters, and options in the proposed code snippet compatible with "
            "the documented parameter names and types?"
        ),
    },
    "support_level": {
        "type": "choice",
        "instructions": "How strongly does the reference document support the code or claim being made?",
        "criteria": {
            "fully_supported": "The document explicitly documents this exact API, method signature, or pattern.",
            "extrapolated": "The document mentions related concepts but not this specific method signature.",
            "contradicted": "The document explicitly specifies a different method signature, deprecation, or prohibition.",
        },
    },
}


def extract_mutation_content(operation: Operation, harness: Harness | str) -> tuple[str, tuple[str, ...]]:
    """Extract code additions or modifications and target paths from an operation."""
    if operation.kind != "file_mutation":
        return "", ()

    args = operation.arguments
    paths = list(operation.paths)

    # Antigravity file mutation tools
    if operation.tool_name in {"replace_file_content", "replace_content"}:
        target = str(args.get("TargetFile") or args.get("target_file") or "")
        if target and target not in paths:
            paths.append(target)
        content = str(args.get("ReplacementContent") or args.get("replacement_content") or "")
        return content, tuple(paths)

    if operation.tool_name in {"write_to_file", "write_file", "create_file"}:
        target = str(args.get("TargetFile") or args.get("target_file") or "")
        if target and target not in paths:
            paths.append(target)
        content = str(args.get("CodeContent") or args.get("code_content") or args.get("content") or "")
        return content, tuple(paths)

    # Codex patch tool (apply_patch)
    if operation.tool_name == "apply_patch":
        patch_text = str(operation.command or args.get("command") or args.get("patch") or "")
        added_lines: list[str] = []
        for line in patch_text.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added_lines.append(line[1:])
        content = "\n".join(added_lines) if added_lines else patch_text
        return content, tuple(paths)

    return "", tuple(paths)


def resolve_reference_context(
    cwd: Path,
    paths: tuple[str, ...],
    knowledge_roots: tuple[Path, ...],
) -> str:
    """Resolve available reference context from local files or active knowledge items."""
    contexts: list[str] = []

    # Check local files for docstrings / header types
    for target in paths:
        candidate = Path(target) if Path(target).is_absolute() else cwd / target
        if candidate.exists() and candidate.is_file():
            try:
                text = candidate.read_text(encoding="utf-8", errors="ignore")
                # Pull top 2000 chars (module docstrings, imports, class defs)
                if text.strip():
                    contexts.append(f"File Context ({candidate.name}):\n{text[:2000]}")
            except Exception:
                pass

    # Check knowledge roots
    for root in knowledge_roots:
        if not root.exists():
            continue
        for ki_file in root.glob("**/KI.md"):
            try:
                ki_text = ki_file.read_text(encoding="utf-8", errors="ignore")
                for target in paths:
                    stem = Path(target).stem.lower()
                    if stem and stem in ki_text.lower():
                        contexts.append(f"Knowledge Item ({ki_file.parent.name}):\n{ki_text[:1500]}")
                        break
            except Exception:
                pass

    return "\n\n".join(contexts[:3])


def evaluate_verification(
    code_snippet: str,
    reference_context: str,
    client: DecisionClient | None,
    timeout: float = 3.0,
) -> dict[str, Any]:
    """Evaluate code snippet against reference context via Jev System One."""
    started = time.monotonic()
    if not code_snippet.strip():
        return {
            "verified": True,
            "method_supported": 1.0,
            "arguments_match": 1.0,
            "support_level": "fully_supported",
            "advisory": None,
            "duration_ms": 0.0,
        }

    if not reference_context.strip() or client is None:
        return {
            "verified": True,
            "method_supported": 0.5,
            "arguments_match": 0.5,
            "support_level": "extrapolated",
            "advisory": None,
            "duration_ms": 0.0,
        }

    state = {
        "code_snippet": redact(code_snippet, 8000),
        "reference_context": redact(reference_context, 10000),
    }

    try:
        answers = client.evaluate(state, QUESTIONS, timeout)
    except Exception as exc:
        duration_ms = round((time.monotonic() - started) * 1000, 2)
        return {
            "verified": True,
            "method_supported": 0.5,
            "arguments_match": 0.5,
            "support_level": "extrapolated",
            "advisory": None,
            "error": f"Verification provider unavailable: {type(exc).__name__}",
            "duration_ms": duration_ms,
        }

    duration_ms = round((time.monotonic() - started) * 1000, 2)

    # Extract answers
    raw_method = answers.get("method_supported_by_docs", 0.5)
    method_supported = (
        float(raw_method.get("noul", raw_method.get("probability", 0.5)))
        if isinstance(raw_method, dict)
        else float(raw_method or 0.5)
    )

    raw_args = answers.get("arguments_match_spec", 0.5)
    arguments_match = (
        float(raw_args.get("noul", raw_args.get("probability", 0.5)))
        if isinstance(raw_args, dict)
        else float(raw_args or 0.5)
    )

    raw_support = answers.get("support_level", "extrapolated")
    if isinstance(raw_support, dict):
        support_level = str(raw_support.get("choice", raw_support.get("selected", "extrapolated")))
    else:
        support_level = str(raw_support or "extrapolated")

    is_contradicted = support_level == "contradicted"
    is_unsupported = method_supported < 0.40 and support_level != "fully_supported"
    verified = not is_contradicted and not is_unsupported

    advisory = None
    if is_contradicted:
        advisory = (
            f"[Jev Verification Advisory] Proposed code is contradicted by reference documentation "
            f"(method support: {method_supported:.2f}). Check library exports and signatures before applying."
        )
    elif is_unsupported:
        advisory = (
            f"[Jev Verification Advisory] Proposed API or method appears unsupported by reference documentation "
            f"(confidence: {method_supported:.2f}, support: {support_level}). Check method signatures."
        )

    return {
        "verified": verified,
        "method_supported": method_supported,
        "arguments_match": arguments_match,
        "support_level": support_level,
        "advisory": advisory,
        "duration_ms": duration_ms,
    }


def evaluate_operation(
    operation: Operation | None,
    event: Event,
    settings: Settings,
    client: DecisionClient | None,
    storage: Storage,
    timeout: float = 3.0,
) -> Result | None:
    """PreToolUse feature handler for code output and citation verification."""
    started = time.monotonic()
    if operation is None:
        return None

    code_content, paths = extract_mutation_content(operation, event.harness)
    if not code_content.strip() or not paths:
        return None

    reference_context = resolve_reference_context(
        Path(event.cwd),
        paths,
        settings.knowledge_roots,
    )

    eval_result = evaluate_verification(code_content, reference_context, client, timeout)
    duration_ms = (time.monotonic() - started) * 1000

    target_path = paths[0] if paths else ""
    advisory = eval_result.get("advisory")

    try:
        storage.record_verification_decision({
            "event_id": event.event_id,
            "session_id": event.session_id,
            "harness": event.harness.value if hasattr(event.harness, "value") else str(event.harness),
            "target_path": target_path,
            "code_snippet": redact(code_content, 2000),
            "method_supported": eval_result["method_supported"],
            "arguments_match": eval_result["arguments_match"],
            "support_level": eval_result["support_level"],
            "advisory_emitted": 1 if advisory else 0,
            "duration_ms": duration_ms,
        })
    except Exception:
        pass

    context_items = []
    if advisory:
        context_items.append(ContextItem(
            feature=VERIFICATION_FEATURE,
            text=advisory,
            priority=80,
        ))

    return Result(
        outcome=Outcome.ALLOW,
        context=context_items,
        feature=VERIFICATION_FEATURE,
        feature_version=VERIFICATION_VERSION,
        duration_ms=duration_ms,
    )
