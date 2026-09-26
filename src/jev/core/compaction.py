"""Harness-neutral transcript checkpoint creation."""

from __future__ import annotations

from typing import Any


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

