"""Harness-neutral transcript checkpoint creation."""

from __future__ import annotations

from typing import Any

from jev.contracts import ContextItem, Event, Result
from jev.services.storage import redact


def context_anchors(event: Event) -> Result:
    """Carry bounded source excerpts through native compaction without rewriting history."""
    limits = {"session_objective": 400, "prior_context": 1000, "active_path": 500, "last_error": 800}
    anchors = {
        key: redact(str(event.payload.get(key) or ""), limit)
        for key, limit in limits.items()
        if event.payload.get(key)
    }
    result = Result(feature="compaction", feature_version="1", data={"anchor_count": len(anchors)})
    if anchors:
        import json

        result.context.append(ContextItem(
            "compaction", "[Jev context anchors; source excerpts, not a complete transcript]\n" +
            json.dumps(anchors, ensure_ascii=False), priority=70,
        ))
    return result


def checkpoint(messages: list[dict[str, Any]], preserve_recent: int = 6, head_chars: int = 300) -> list[dict[str, Any]]:
    """Create a sidecar-safe checkpoint without modifying a harness transcript."""
    if len(messages) <= preserve_recent + 1:
        return messages
    pinned = {0, *range(max(1, len(messages) - preserve_recent), len(messages))}
    output: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        if index in pinned or message.get("role") == "user":
            output.append(message)
            continue
        copied = dict(message)
        calls = []
        for call in message.get("tool_calls", []):
            item = dict(call)
            if "result" in item:
                raw = str(item["result"])
                item["result"] = raw[:head_chars] + ("\n[Checkpoint truncated; rerun tool for full output.]" if len(raw) > head_chars else "")
            calls.append(item)
        copied["tool_calls"] = calls
        output.append(copied)
    return output
