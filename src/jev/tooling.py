"""Callable tools shared by MCP and direct Python users."""

from __future__ import annotations

from jev.core import knowledge, skills
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


def skills_list(settings: Settings) -> list[dict[str, str]]:
    """List skills from the canonical skill catalog."""
    return skills.list_skills(settings.skill_roots)


def diagnostics_status(settings: Settings) -> dict:
    """Report runtime paths and registered capabilities."""
    return report(settings)


HANDLERS = {
    "knowledge_search": knowledge_search,
    "knowledge_learn": knowledge_learn,
    "skills_list": skills_list,
    "diagnostics_status": diagnostics_status,
}

