"""OpenCode plugin bridge adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from jev.adapters.base import Adapter, patch_paths, stable_event_id, workspace_id
from jev.contracts import Event, EventKind, Harness, Operation, Outcome, Result


FILE_TOOLS = {"write", "edit", "multiedit", "apply_patch", "patch"}


class OpenCodeAdapter(Adapter):
    harness = Harness.OPENCODE

    def decode(self, raw: Mapping[str, Any]) -> tuple[Event, Operation | None]:
        native_event = str(raw.get("opencode_event") or "")
        if native_event == "session.start":
            kind = EventKind.SESSION_START
        elif native_event == "turn.before":
            kind = EventKind.TURN_BEFORE
        elif native_event == "tool.execute.before":
            kind = EventKind.TOOL_BEFORE
        else:
            raise ValueError(f"Unsupported OpenCode event: {native_event or '<missing>'}")

        cwd = str(raw.get("cwd") or Path.cwd())
        session_id = str(raw.get("session_id") or "")
        turn_id = str(raw.get("message_id") or raw.get("turn_id") or "")
        tool_call_id = str(raw.get("call_id") or "")
        event_id = stable_event_id(
            (session_id, turn_id, native_event, tool_call_id), raw
        )
        prompt = str(raw.get("prompt") or "")
        payload = {
            "prompt": prompt,
            "prior_context": str(raw.get("prior_context") or ""),
            "session_objective": str(raw.get("session_objective") or ""),
            "active_path": str(raw.get("active_path") or ""),
            "last_error": str(raw.get("last_error") or ""),
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
            agent_id=str(raw.get("agent") or ""),
            invocation_id=tool_call_id or turn_id,
            tool_call_id=tool_call_id,
            deadline_monotonic=self._deadline(),
        )
        if kind != EventKind.TOOL_BEFORE:
            return event, None

        tool_name = str(raw.get("tool") or "")
        tool_input = raw.get("args") or {}
        if not isinstance(tool_input, Mapping):
            raise ValueError("OpenCode tool args must be an object")

        if tool_name == "bash":
            operation = Operation(
                kind="shell",
                tool_name="Bash",
                command=str(tool_input.get("command") or ""),
                arguments=dict(tool_input),
            )
            if not operation.command:
                raise ValueError("OpenCode bash hook omitted args.command")
            return event, operation

        if tool_name in FILE_TOOLS:
            patch = str(
                tool_input.get("patch")
                or tool_input.get("patchText")
                or tool_input.get("command")
                or ""
            )
            paths = list(patch_paths(patch)) if tool_name in {"apply_patch", "patch"} else []
            for key in ("filePath", "file_path", "path"):
                value = tool_input.get(key)
                if isinstance(value, str) and value:
                    paths.append(value)
            edits = tool_input.get("edits")
            if isinstance(edits, list):
                paths.extend(
                    str(item.get("filePath") or item.get("file_path") or item.get("path"))
                    for item in edits
                    if isinstance(item, Mapping)
                    and (item.get("filePath") or item.get("file_path") or item.get("path"))
                )
            operation = Operation(
                kind="file_mutation",
                tool_name=tool_name,
                arguments=dict(tool_input),
                paths=tuple(dict.fromkeys(paths)),
            )
            return event, operation

        operation = Operation(
            kind="tool",
            tool_name=tool_name,
            arguments=dict(tool_input),
        )
        return event, operation

    def encode(self, event: Event, result: Result) -> dict[str, Any]:
        context = "\n\n".join(item.text for item in result.context)
        if event.kind in {EventKind.SESSION_START, EventKind.TURN_BEFORE}:
            return {"context": context}
        if event.kind == EventKind.TOOL_BEFORE:
            denied = result.outcome in {Outcome.DENY, Outcome.NEEDS_CONFIRMATION}
            return {
                "deny": denied,
                "reason": result.reason or "Jev policy denied this operation.",
                "context": context,
            }
        return {}
