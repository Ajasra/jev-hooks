"""OpenAI Codex lifecycle hook adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from jev.adapters.base import Adapter, extract_turn_context, patch_paths, stable_event_id, workspace_id
from jev.contracts import Event, EventKind, Harness, Operation, Outcome, Result


EVENTS = {
    "SessionStart": EventKind.SESSION_START,
    "UserPromptSubmit": EventKind.TURN_BEFORE,
    "PreToolUse": EventKind.TOOL_BEFORE,
    "PostToolUse": EventKind.TOOL_AFTER,
    "PreCompact": EventKind.CONTEXT_CHECKPOINT,
    "PostCompact": EventKind.CONTEXT_CHECKPOINT,
    "SessionEnd": EventKind.SESSION_END,
}


class CodexAdapter(Adapter):
    harness = Harness.CODEX

    def decode(self, raw: Mapping[str, Any]) -> tuple[Event, Operation | None]:
        native_event = str(raw.get("hook_event_name") or "")
        if native_event not in EVENTS:
            raise ValueError(f"Unsupported Codex event: {native_event or '<missing>'}")
        kind = EVENTS[native_event]
        cwd = str(raw.get("cwd") or Path.cwd())
        session_id = str(raw.get("session_id") or "")
        turn_id = str(raw.get("turn_id") or "")
        tool_name = str(raw.get("tool_name") or "")
        tool_input = raw.get("tool_input") or {}
        if not isinstance(tool_input, Mapping):
            raise ValueError("Codex tool_input must be an object")
        tool_call_id = str(raw.get("tool_use_id") or "")
        invocation = tool_call_id or turn_id
        event_id = stable_event_id((session_id, turn_id, native_event, tool_call_id), raw)
        transcript_path = str(raw.get("transcript_path") or raw.get("transcriptPath") or "")
        transcript_context = extract_turn_context(transcript_path) if transcript_path else {}
        prompt = str(raw.get("prompt") or transcript_context.get("current_prompt") or "")
        prior_context = str(raw.get("prior_context") or raw.get("priorContext") or transcript_context.get("prior_prompt") or "")
        payload = {
            "prompt": prompt,
            "prior_context": prior_context,
            "transcript_path": transcript_path,
            "trigger": str(raw.get("trigger") or ""),
            "native": dict(raw),
        }
        event = Event(
            kind=kind,
            harness=self.harness,
            event_id=event_id,
            workspace_id=workspace_id(cwd),
            session_id=session_id,
            cwd=str(Path(cwd).resolve()),
            payload=payload,
            harness_version=str(raw.get("harness_version") or ""),
            turn_id=turn_id,
            agent_id=str(raw.get("agent_id") or ""),
            invocation_id=invocation,
            tool_call_id=tool_call_id,
            deadline_monotonic=self._deadline(),
        )
        if kind not in {EventKind.TOOL_BEFORE, EventKind.TOOL_AFTER}:
            return event, None
        command = str(tool_input.get("command") or "")
        if tool_name == "Bash" and not command:
            raise ValueError("Codex Bash hook omitted tool_input.command")
        is_patch = tool_name == "apply_patch"
        paths = patch_paths(command) if is_patch else ()
        operation = Operation(
            kind="file_mutation" if is_patch else "shell" if tool_name == "Bash" else "tool",
            tool_name=tool_name,
            command="" if is_patch else command,
            arguments=dict(tool_input),
            paths=paths,
        )
        return event, operation

    def encode(self, event: Event, result: Result) -> dict[str, Any]:
        context = "\n\n".join(item.text for item in result.context)
        if event.kind == EventKind.TURN_BEFORE:
            if not context:
                return {}
            telemetry_footer = (
                f"\n\n<!-- jev-telemetry: {len(result.context)} item(s) injected | "
                f"outcome: {result.outcome.value} | latency: {result.duration_ms:.1f}ms -->"
            )
            return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context + telemetry_footer}}
        if event.kind == EventKind.SESSION_START:
            if not context:
                return {}
            return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}
        if event.kind == EventKind.TOOL_BEFORE:
            if result.outcome in {Outcome.DENY, Outcome.NEEDS_CONFIRMATION}:
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": result.reason or "Jev policy denied this operation.",
                    }
                }
            if context:
                return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": context}}
            return {}
        if event.kind == EventKind.TOOL_AFTER:
            return {"systemMessage": context} if context else {}
        return {}

