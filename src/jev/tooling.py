"""Callable tools shared by MCP and direct Python users."""

from __future__ import annotations

from typing import Any

from jev.core import knowledge, skills
from jev.core import semantic_lint as semantic_lint_core
from jev.install.doctor import report
from jev.services.paths import Settings


def knowledge_search(settings: Settings, query: str) -> dict:
    """Search repository knowledge items for a query."""
    return knowledge.search(query, settings.knowledge_roots).to_dict()


def knowledge_learn(settings: Settings, summary: str, details: str) -> dict:
    """Explicitly save a repository knowledge item."""
    if not settings.knowledge_roots:
        raise ValueError("No knowledge root is configured")
    return knowledge.learn(summary, details, settings.knowledge_roots[0])


def record_gotcha(
    settings: Settings,
    title: str,
    trap: str = "",
    remediation: str = "",
    tags: list[str] | str | None = None,
    slug: str | None = None,
    **kwargs: Any,
) -> dict:
    """Persist an operational gotcha into repository docs/gotchas/."""
    gotchas_root = settings.workspace_root / "docs" / "gotchas"
    return knowledge.record_gotcha(
        title=title,
        trap=trap or str(kwargs.get("summary", "")),
        remediation=remediation or str(kwargs.get("details", "")),
        root=gotchas_root,
        tags=tags,
        slug=slug,
    )


def skills_list(settings: Settings) -> list[dict[str, str]]:
    """List skills from the canonical skill catalog."""
    return skills.list_skills(settings.skill_roots)


def diagnostics_status(settings: Settings) -> dict:
    """Report runtime paths and registered capabilities."""
    return report(settings)


def semantic_lint(settings: Settings, staged: bool = True, base_ref: str | None = None) -> dict:
    from jev.services.client import HttpDecisionClient
    from jev.services.storage import Storage
    return semantic_lint_core.evaluate(
        workspace=settings.workspace_root, roots=settings.lint_rule_roots,
        storage=Storage(settings.db_path), client=HttpDecisionClient.from_environment(),
        harness=settings.harness_identity, workspace_id=str(settings.workspace_root),
        staged=staged, base_ref=base_ref, timeout=settings.semantic_timeout_seconds,
    )


def semantic_lint_feedback(settings: Settings, decision_id: int, label: str, reason: str = "") -> dict:
    from jev.services.storage import Storage
    Storage(settings.db_path).record_semantic_lint_feedback(decision_id, label, reason)
    return {"success": True, "decision_id": decision_id, "label": label}


def semantic_lint_stats(settings: Settings, rule_id: str | None = None) -> dict:
    from jev.services.storage import Storage
    return Storage(settings.db_path).semantic_lint_stats(rule_id)


def verify_output(settings: Settings, code_snippet: str, reference_context: str) -> dict:
    """Verify proposed code or citations against reference documentation."""
    from jev.core.verification import evaluate_verification
    from jev.services.client import HttpDecisionClient
    client = HttpDecisionClient.from_environment()
    return evaluate_verification(code_snippet, reference_context, client, timeout=settings.semantic_timeout_seconds)


def verify_completion(settings: Settings, claim_text: str, session_id: str = "") -> dict:
    """Validate completion claim against WHAT-WHY-HOW-LEARNINGS schema and tool executions."""
    from jev.core.verification import verify_completion_claim
    from jev.services.storage import Storage
    return verify_completion_claim(claim_text, session_id, Storage(settings.db_path))


HANDLERS = {
    "knowledge_search": knowledge_search,
    "knowledge_learn": knowledge_learn,
    "record_gotcha": record_gotcha,
    "skills_list": skills_list,
    "diagnostics_status": diagnostics_status,
    "semantic_lint": semantic_lint,
    "semantic_lint_feedback": semantic_lint_feedback,
    "semantic_lint_stats": semantic_lint_stats,
    "verify_output": verify_output,
    "verify_completion": verify_completion,
}
