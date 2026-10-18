"""Shared feature dispatcher used by every harness adapter and tool transport."""

from __future__ import annotations

import time
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from jev.contracts import Event, EventKind, Harness, Operation, Outcome, Result, merge_results
from jev.core import context, knowledge, loop_guard, safety, skills, speculative, verification
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
        # Leave headroom below the native five-second process timeout. Start the
        # dispatch budget here so time spent waiting after decoding does not count.
        started = time.monotonic()
        deadline = started + 4.0
        event = replace(event, deadline_monotonic=min(event.deadline_monotonic, deadline)
                        if event.deadline_monotonic is not None else deadline)
        results: list[Result] = []
        envelope = None
        if event.kind in {EventKind.TURN_BEFORE, EventKind.SESSION_START}:
            envelope = context.assemble_envelope(event, Path(event.cwd))
        turn_results = self._enrich_turn(event, envelope) if event.kind == EventKind.TURN_BEFORE else {}


        for spec in sorted(FEATURES, key=lambda item: -item.priority):
            if event.kind not in spec.triggers:
                continue
            if spec.id in turn_results:
                results.append(turn_results[spec.id])
                continue
            if (spec.handler_name != "safety" and event.deadline_monotonic is not None
                    and time.monotonic() >= event.deadline_monotonic):
                results.append(Result(feature=spec.id, feature_version=spec.version, timed_out=True,
                                      reason_code="dispatch_deadline_exceeded"))
                continue
            if spec.handler_name == "safety":
                results.append(self._safety(event, operation))
            elif spec.handler_name == "loop_guard":
                if event.kind == EventKind.TOOL_BEFORE:
                    lg_res = loop_guard.evaluate_before(event, operation, self.storage)
                    if lg_res is not None and lg_res.outcome != Outcome.ABSTAIN:
                        results.append(lg_res)
                elif event.kind == EventKind.TOOL_AFTER:
                    results.append(loop_guard.record_after(event, operation, self.storage))
            elif spec.handler_name == "verification":
                v_res = verification.evaluate_operation(
                    operation,
                    event,
                    self.settings,
                    self.client,
                    self.storage,
                    self._remaining(event),
                )
                if v_res is not None:
                    results.append(v_res)
            elif spec.handler_name == "knowledge":
                semantic_prompt = envelope.to_semantic_string() if envelope else str(event.payload.get("prompt", ""))
                results.append(knowledge.search(
                    semantic_prompt,
                    self.settings.knowledge_roots,
                    self.client,
                    self._remaining(event),
                ))
        merged = merge_results(results, self.settings.context_budget)
        if envelope:
            envelope_telemetry = envelope.to_telemetry()
            merged.data["context_telemetry"] = envelope_telemetry
            for result in results:
                result.data["context_telemetry"] = envelope_telemetry

        for result in results:
            retained = [item for item in merged.context if item.feature == result.feature]
            result.data.update({
                "context_items_proposed": len(result.context),
                "context_items_injected": len(retained),
                "context_chars_injected": sum(len(item.text) for item in retained),
            })
            try:
                self.storage.record_event(event, result)
            except Exception:
                pass
        merged.duration_ms = (time.monotonic() - started) * 1000
        return merged

    def _enrich_turn(self, event: Event, envelope) -> dict[str, Result]:
        """Independent, read-only enrichers share a budget without serial starvation."""
        if event.deadline_monotonic is not None and time.monotonic() >= event.deadline_monotonic:
            return {}
        prompt = envelope.to_semantic_string()
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="jev-advisory") as pool:
            pending = {
                "speculative": pool.submit(
                    speculative.evaluate, envelope.prompt, Path(event.cwd),
                    envelope.prior_context, self.client, self._remaining(event),
                ),
                "skills": pool.submit(
                    skills.suggest, prompt, self.settings.skill_roots, self.client,
                    self._remaining(event), inject_body=event.harness != Harness.CODEX,
                ),
                "knowledge": pool.submit(
                    knowledge.search, prompt, self.settings.knowledge_roots,
                    self.client, self._remaining(event),
                ),
            }
            return {name: future.result() for name, future in pending.items()}

    def _remaining(self, event: Event) -> float:
        if event.deadline_monotonic is None:
            return self.settings.semantic_timeout_seconds
        return max(0.0, min(self.settings.semantic_timeout_seconds, event.deadline_monotonic - time.monotonic()))

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
                result = self.storage.complete_claim(event, "safety", event.kind.value, result, rule_id, digest=digest)
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
