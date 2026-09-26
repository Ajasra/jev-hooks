"""Harness-neutral event and result contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping


SCHEMA_VERSION = 1


class Harness(str, Enum):
    ANTIGRAVITY = "antigravity"
    CODEX = "codex"


class EventKind(str, Enum):
    SESSION_START = "session.start"
    TURN_BEFORE = "turn.before"
    TOOL_BEFORE = "tool.before"
    TOOL_AFTER = "tool.after"
    CONTEXT_CHECKPOINT = "context.checkpoint"
    SESSION_END = "session.end"


class Outcome(str, Enum):
    ABSTAIN = "abstain"
    ALLOW = "allow"
    NEEDS_CONFIRMATION = "needs_confirmation"
    DENY = "deny"


OUTCOME_PRIORITY = {
    Outcome.ABSTAIN: 0,
    Outcome.ALLOW: 1,
    Outcome.NEEDS_CONFIRMATION: 2,
    Outcome.DENY: 3,
}


@dataclass(frozen=True)
class Operation:
    kind: str
    tool_name: str
    command: str = ""
    arguments: Mapping[str, Any] = field(default_factory=dict)
    paths: tuple[str, ...] = ()
    shell: str = ""


@dataclass(frozen=True)
class Event:
    kind: EventKind
    harness: Harness
    event_id: str
    workspace_id: str
    session_id: str
    cwd: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    harness_version: str = ""
    turn_id: str = ""
    agent_id: str = ""
    invocation_id: str = ""
    tool_call_id: str = ""
    deadline_monotonic: float | None = None
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class ContextItem:
    feature: str
    text: str
    priority: int = 0


@dataclass
class Result:
    outcome: Outcome = Outcome.ABSTAIN
    reason: str = ""
    reason_code: str = ""
    context: list[ContextItem] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    feature: str = ""
    feature_version: str = ""
    source: str = "core"
    duration_ms: float = 0.0
    timed_out: bool = False
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["outcome"] = self.outcome.value
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Result":
        contexts = [ContextItem(**item) for item in value.get("context", [])]
        return cls(
            outcome=Outcome(value.get("outcome", "abstain")),
            reason=str(value.get("reason", "")),
            reason_code=str(value.get("reason_code", "")),
            context=contexts,
            data=dict(value.get("data", {})),
            feature=str(value.get("feature", "")),
            feature_version=str(value.get("feature_version", "")),
            source=str(value.get("source", "core")),
            duration_ms=float(value.get("duration_ms", 0.0)),
            timed_out=bool(value.get("timed_out", False)),
            error=str(value.get("error", "")),
        )


def merge_results(results: list[Result], context_budget: int = 12_000) -> Result:
    """Merge feature results deterministically without weakening policy."""
    if not results:
        return Result()
    strongest = max(results, key=lambda item: OUTCOME_PRIORITY[item.outcome])
    merged = Result(
        outcome=strongest.outcome,
        reason=strongest.reason,
        reason_code=strongest.reason_code,
        feature="runtime",
        feature_version="1",
        source="aggregate",
        timed_out=any(item.timed_out for item in results),
        error="; ".join(item.error for item in results if item.error),
    )
    remaining = max(context_budget, 0)
    items = sorted(
        (context for result in results for context in result.context),
        key=lambda item: (-item.priority, item.feature, item.text),
    )
    for item in items:
        if remaining <= 0:
            break
        text = item.text[:remaining]
        if text:
            merged.context.append(ContextItem(item.feature, text, item.priority))
            remaining -= len(text)
    merged.data = {item.feature: item.data for item in results if item.feature and item.data}
    merged.duration_ms = sum(item.duration_ms for item in results)
    return merged

