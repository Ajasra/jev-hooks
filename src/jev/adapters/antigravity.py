"""Antigravity JSON adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from jev.adapters.base import Adapter, extract_turn_context, stable_event_id, workspace_id
from jev.contracts import Event, EventKind, Harness, Operation, Outcome, Result
from jev.core.safety import clean_command


TURN_EVENTS = {"PreInvocation": EventKind.TURN_BEFORE}
TOOL_EVENTS = {"PreToolUse": EventKind.TOOL_BEFORE, "PostToolUse": EventKind.TOOL_AFTER}


class AntigravityAdapter(Adapter):
    harness = Harness.ANTIGRAVITY

    def decode(self, raw: Mapping[str, Any]) -> tuple[Event, Operation | None]:
        native_event = str(raw.get("hookEventName") or raw.get("eventName") or "")
        if native_event in TOOL_EVENTS or raw.get("toolCall"):
            kind = TOOL_EVENTS.get(native_event, EventKind.TOOL_BEFORE)
        else:
            kind = TURN_EVENTS.get(native_event, EventKind.TURN_BEFORE)
        cwd = str((raw.get("workspacePaths") or [raw.get("cwd") or Path.cwd()])[0])
        session_id = str(raw.get("conversationId") or raw.get("sessionId") or "")
        invocation = str(raw.get("invocationId") or raw.get("invocationNum") or "")
        tool_call = raw.get("toolCall") if isinstance(raw.get("toolCall"), Mapping) else {}
        tool_name = str(tool_call.get("name") or raw.get("tool_name") or "")
        arguments = tool_call.get("args") or raw.get("args") or {}
        if not isinstance(arguments, Mapping):
            arguments = {"value": arguments}
        event_id = stable_event_id((session_id, invocation, native_event, tool_name), raw)
        transcript_path = raw.get("transcriptPath") or raw.get("transcript_path")
        transcript_context = extract_turn_context(transcript_path) if transcript_path else {}
        prompt = str(raw.get("prompt") or transcript_context.get("current_prompt") or "")
        prior_context = str(raw.get("priorContext") or raw.get("prior_context") or transcript_context.get("prior_prompt") or "")
        payload = {
            "prompt": prompt,
            "prior_context": prior_context,
            "session_objective": str(raw.get("session_objective") or transcript_context.get("session_objective") or ""),
            "active_path": str(raw.get("active_path") or transcript_context.get("active_file") or ""),
            "last_error": str(raw.get("last_error") or transcript_context.get("last_error") or ""),
            "transcript_path": str(transcript_path or ""),
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
            harness_version=str(raw.get("harnessVersion") or ""),
            turn_id=str(raw.get("turnId") or invocation),
            agent_id=str(raw.get("agentId") or raw.get("agent") or ""),
            invocation_id=invocation,
            tool_call_id=str(tool_call.get("id") or raw.get("toolUseId") or ""),
            deadline_monotonic=self._deadline(),
        )
        if kind not in {EventKind.TOOL_BEFORE, EventKind.TOOL_AFTER}:
            return event, None
        command = str(arguments.get("CommandLine") or arguments.get("command") or "")
        path = str(arguments.get("TargetFile") or arguments.get("file_path") or "")
        is_file = tool_name in {"write_to_file", "replace_file_content", "multi_replace_file_content"}
        operation = Operation(
            kind="file_mutation" if is_file else "shell" if tool_name == "run_command" else "tool",
            tool_name=tool_name,
            command=command,
            arguments=dict(arguments),
            paths=(path,) if path else (),
            shell="cmd" if command.lower().startswith(("cmd ", "cmd.exe ")) else "",
        )
        return event, operation

    def encode(self, event: Event, result: Result) -> dict[str, Any]:
        context = "\n\n".join(item.text for item in result.context)
        if event.kind == EventKind.TURN_BEFORE:
            if not context:
                return {}
            # Append lightweight Jev reflex telemetry info for transparency and performance insight
            telemetry_footer = (
                f"\n\n<!-- jev-telemetry: {len(result.context)} item(s) injected | "
                f"outcome: {result.outcome.value} | latency: {result.duration_ms:.1f}ms -->"
            )
            return {"injectSteps": [{"ephemeralMessage": context + telemetry_footer}]}
        if event.kind == EventKind.TOOL_BEFORE:
            if result.outcome == Outcome.DENY:
                return {"decision": "deny", "reason": result.reason}
            if result.outcome == Outcome.NEEDS_CONFIRMATION:
                return {"decision": "force_ask", "reason": result.reason}
            output: dict[str, Any] = {"decision": "allow", "reason": result.reason}
            native_args: Mapping[str, Any] = {}
            native = event.payload.get("native")
            if isinstance(native, Mapping):
                tool_call = native.get("toolCall")
                if isinstance(tool_call, Mapping) and isinstance(tool_call.get("args"), Mapping):
                    native_args = tool_call["args"]
                elif isinstance(native.get("args"), Mapping):
                    native_args = native["args"]
            cmd = str(native_args.get("CommandLine") or native_args.get("command") or "").strip()
            if cmd:
                overrides = [f"command({cmd})"]
                cleaned = clean_command(cmd)
                if cleaned and cleaned != cmd:
                    overrides.append(f"command({cleaned})")
                output["permissionOverrides"] = overrides
            if context:
                output["additionalContext"] = context
            return output
        return {"injectSteps": [{"ephemeralMessage": context}]} if context else {}

