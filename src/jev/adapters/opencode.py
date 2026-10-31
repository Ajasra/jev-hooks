"""OpenCode lifecycle hook adapter (payload contract per RFC-27 5.3-5.4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from jev.adapters.base import Adapter, patch_paths, stable_event_id, tool_result_payload, workspace_id
from jev.contracts import Event, EventKind, Harness, HarnessCapabilities, Operation, Outcome, Result

EVENTS = {
    "session.start": EventKind.SESSION_START,
    "session.deleted": EventKind.SESSION_END,
    "chat.message": EventKind.TURN_BEFORE,
    "turn.before": EventKind.TURN_BEFORE,
    "tool.execute.before": EventKind.TOOL_BEFORE,
    "tool.execute.after": EventKind.TOOL_AFTER,
    "experimental.session.compacting": EventKind.CONTEXT_CHECKPOINT,
}

FILE_MUTATION_TOOLS = frozenset({"write", "edit", "apply_patch"})


def _telemetry(result: Result, count: int) -> str:
    return (
        f"<!-- jev-telemetry: {count} item(s) injected | "
        f"outcome: {result.outcome.value} | latency: {result.duration_ms:.1f}ms -->"
    )


class OpenCodeAdapter(Adapter):
    harness = Harness.OPENCODE
    capabilities = HarnessCapabilities(native_skills=True)

    def decode(self, raw: Mapping[str, Any]) -> tuple[Event, Operation | None]:
        hook = str(raw.get("hook") or raw.get("opencode_event") or "")
        if hook not in EVENTS:
            raise ValueError(f"Unsupported OpenCode hook: {hook or '<missing>'}")
        kind = EVENTS[hook]
        cwd = str(raw.get("cwd") or Path.cwd())
        session_id = str(raw.get("session_id") or "")
        turn_id = str(raw.get("turn_id") or "")
        native = raw.get("native")
        tool = raw.get("tool") if isinstance(raw.get("tool"), Mapping) else {}
        tool_name = str(tool.get("name") or (raw.get("tool") if isinstance(raw.get("tool"), str) else "") or "")
        call_id = str(tool.get("call_id") or raw.get("call_id") or "")
        payload: dict[str, Any] = {
            "prompt": str(raw.get("prompt") or ""),
            "prior_context": str(raw.get("prior_context") or "")[:1000],
            "session_objective": str(raw.get("session_objective") or "")[:400],
            "active_path": str(raw.get("active_path") or "")[:500],
            "last_error": str(raw.get("last_error") or "")[:800],
            "transcript_path": "",
            "native": dict(native) if isinstance(native, Mapping) else {},
        }
        if kind == EventKind.TOOL_AFTER:
            result = raw.get("result")
            if isinstance(result, Mapping):
                payload["result"] = dict(result)
            payload.update(tool_result_payload(raw))
        event = Event(
            capabilities=self.capabilities,
            kind=kind,
            harness=self.harness,
            event_id=stable_event_id((session_id, turn_id, hook, call_id), raw),
            workspace_id=workspace_id(cwd),
            session_id=session_id,
            cwd=str(Path(cwd).resolve()),
            payload=payload,
            harness_version=str(raw.get("harness_version") or ""),
            turn_id=turn_id,
            agent_id=str(raw.get("agent") or ""),
            invocation_id=call_id or turn_id,
            tool_call_id=call_id,
            deadline_monotonic=self._deadline(),
        )
        if kind not in {EventKind.TOOL_BEFORE, EventKind.TOOL_AFTER}:
            return event, None
        if not tool_name:
            raise ValueError("OpenCode tool hook omitted tool.name")
        args = tool.get("args") if isinstance(tool.get("args"), Mapping) else raw.get("args")
        if not isinstance(args, Mapping):
            raise ValueError(f"OpenCode tool {tool_name} omitted tool.args")
        command = str(args.get("command") or "")
        if tool_name == "bash" and not command:
            raise ValueError("OpenCode bash hook omitted args.command")
        paths: tuple[str, ...] = ()
        if tool_name in FILE_MUTATION_TOOLS:
            if tool_name == "apply_patch":
                patch = str(args.get("patchText") or "")
                if not patch:
                    raise ValueError("OpenCode apply_patch hook omitted args.patchText")
                paths = patch_paths(patch)
            else:
                file_path = str(args.get("filePath") or "")
                if not file_path:
                    raise ValueError(f"OpenCode {tool_name} hook omitted args.filePath")
                paths = (file_path,)
        operation = Operation(
            kind="file_mutation" if tool_name in FILE_MUTATION_TOOLS else "shell" if tool_name == "bash" else "tool",
            tool_name=tool_name,
            command=command,
            arguments=dict(args),
            paths=paths,
            shell=str(args.get("shell") or ""),
        )
        return event, operation

    def encode(self, event: Event, result: Result) -> dict[str, Any]:
        context = "\n\n".join(item.text for item in result.context)
        decision = "deny" if result.outcome == Outcome.DENY else "ask" if result.outcome == Outcome.NEEDS_CONFIRMATION else "allow"
        output: dict[str, Any] = {
            "decision": decision,
            "reason": result.reason,
            "reason_code": result.reason_code,
            "context": "",
            "footer": "",
            "checkpoint_context": [],
        }
        if event.kind == EventKind.TURN_BEFORE:
            if context:
                output["context"] = context + "\n\n" + _telemetry(result, len(result.context))
        elif event.kind == EventKind.TOOL_BEFORE:
            if context:
                output["context"] = context
        elif event.kind == EventKind.TOOL_AFTER:
            output["footer"] = (context + "\n\n" if context else "") + _telemetry(result, len(result.context))
        elif event.kind == EventKind.CONTEXT_CHECKPOINT:
            output["checkpoint_context"] = [item.text for item in result.context]
        return output
