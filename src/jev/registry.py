"""Single registry for hook features and callable tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, FrozenSet

from jev.contracts import EventKind


@dataclass(frozen=True)
class FeatureSpec:
    id: str
    version: str
    triggers: FrozenSet[EventKind]
    handler_name: str
    required_capabilities: FrozenSet[str]
    priority: int
    context_budget: int
    failure_policy: str


FEATURES = (
    FeatureSpec("safety", "safety-v1", frozenset({EventKind.TOOL_BEFORE}), "safety", frozenset({"tool.before"}), 100, 0, "secure"),
    FeatureSpec("verification", "1", frozenset({EventKind.TOOL_BEFORE}), "verification", frozenset({"tool.before", "context"}), 80, 2000, "open"),
    FeatureSpec("speculative", "1", frozenset({EventKind.TURN_BEFORE}), "speculative", frozenset({"turn.before", "context"}), 70, 4000, "open"),
    FeatureSpec("skills", "1", frozenset({EventKind.TURN_BEFORE}), "skills", frozenset({"turn.before", "context"}), 60, 6000, "open"),
    FeatureSpec("knowledge", "1", frozenset({EventKind.TURN_BEFORE, EventKind.SESSION_START}), "knowledge", frozenset({"context"}), 50, 6000, "open"),
)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    handler_name: str
    mutating: bool
    description: str


TOOLS = (
    ToolSpec("knowledge_search", "knowledge_search", False, "Search repository knowledge items."),
    ToolSpec("knowledge_learn", "knowledge_learn", True, "Explicitly save a repository knowledge item."),
    ToolSpec("skills_list", "skills_list", False, "List skills from the canonical catalog."),
    ToolSpec("diagnostics_status", "diagnostics_status", False, "Report Jev runtime paths and capabilities."),
    ToolSpec("semantic_lint", "semantic_lint", False, "Evaluate a Git diff against repository semantic rules."),
    ToolSpec("semantic_lint_feedback", "semantic_lint_feedback", True, "Record user feedback for a semantic lint decision."),
    ToolSpec("semantic_lint_stats", "semantic_lint_stats", False, "Summarize semantic lint effectiveness by rule and version."),
    ToolSpec("verify_output", "verify_output", False, "Verify proposed code or citations against reference documentation."),
)
