"""Shared feature dispatcher used by every harness adapter and tool transport."""

from __future__ import annotations

import time
from pathlib import Path

from jev.contracts import Event, EventKind, Harness, Operation, Outcome, Result, merge_results
from jev.core import knowledge, safety, skills, speculative
from jev.registry import FEATURES
from jev.services.client import DecisionClient, HttpDecisionClient
from jev.services.paths import Settings
from jev.services.storage import Storage, operation_digest


class Runtime:
    def __init__(
        self,
        settings: Settings,
        storage: Storage | None = None,
        client: DecisionClient | None = None,
    ):
        self.settings = settings
        self.storage = storage or Storage(settings.db_path)
        self.client = client if client is not None else HttpDecisionClient.from_environment()

    def dispatch(self, event: Event, operation: Operation | None = None) -> Result:
        results: list[Result] = []
        for spec in sorted(FEATURES, key=lambda item: -item.priority):
            if event.kind not in spec.triggers:
                continue
            if event.deadline_monotonic is not None and time.monotonic() >= event.deadline_monotonic:
                results.append(Result(feature=spec.id, feature_version=spec.version, timed_out=True))
                continue
            if spec.handler_name == "safety":
                results.append(self._safety(event, operation))
            elif spec.handler_name == "speculative":
                results.append(speculative.evaluate(
                    str(event.payload.get("prompt", "")),
                    Path(event.cwd),
                    str(event.payload.get("prior_context", "")),
                    self.client,
                    self._remaining(event),
                ))
            elif spec.handler_name == "skills":
                results.append(skills.suggest(
                    str(event.payload.get("prompt", "")),
                    self.settings.skill_roots,
                    self.client,
                    self._remaining(event),
                    inject_body=event.harness != Harness.CODEX,
                ))
            elif spec.handler_name == "knowledge":
                results.append(knowledge.search(
                    str(event.payload.get("prompt", "")),
                    self.settings.knowledge_roots,
                    self.client,
                    self._remaining(event),
                ))
        merged = merge_results(results, self.settings.context_budget)
        for result in results:
            try:
                self.storage.record_event(event, result)
            except Exception:
                pass
        return merged

    def _remaining(self, event: Event) -> float:
        if event.deadline_monotonic is None:
            return self.settings.semantic_timeout_seconds
        return max(0.05, min(self.settings.semantic_timeout_seconds, event.deadline_monotonic - time.monotonic()))

    def _safety(self, event: Event, operation: Operation | None) -> Result:
        if operation is None or not operation.tool_name:
            return Result(
                outcome=Outcome.DENY,
                reason="Jev could not inspect the pending tool operation.",
                reason_code="malformed_tool_event",
                feature="safety",
                feature_version=safety.POLICY_VERSION,
            )
        digest = operation_digest(operation.tool_name, operation.command, operation.arguments)
        claimed = False
        try:
            claim = self.storage.claim(event, "safety", event.kind.value, digest, safety.POLICY_VERSION)
            if claim.status == "replay" and claim.result is not None:
                return claim.result
            if claim.status == "active":
                return Result(
                    outcome=Outcome.DENY,
                    reason="An identical safety evaluation is still in progress; retry the tool call.",
                    reason_code="safety_claim_active",
                    feature="safety",
                    feature_version=safety.POLICY_VERSION,
                )
            claimed = claim.status == "acquired"
        except Exception:
            claimed = False
        result, rule_id = safety.evaluate(
            event, operation, self.storage, self.client, self._remaining(event)
        )
        if rule_id is not None and not claimed:
            return Result(
                outcome=Outcome.DENY,
                reason="Jev could not claim the one-use authorization atomically; retry after checking storage.",
                reason_code="authorization_claim_failed",
                feature="safety",
                feature_version=safety.POLICY_VERSION,
            )
        if claimed:
            try:
                result = self.storage.complete_claim(event, "safety", event.kind.value, result, rule_id)
            except Exception:
                if result.outcome == Outcome.ALLOW and rule_id is not None:
                    return Result(
                        outcome=Outcome.DENY,
                        reason="Jev could not atomically consume the authorization; retry after checking storage.",
                        reason_code="authorization_commit_failed",
                        feature="safety",
                        feature_version=safety.POLICY_VERSION,
                    )
        return result
