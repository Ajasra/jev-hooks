"""Shared deterministic and semantic safety policy."""

from __future__ import annotations

import re
import time
from pathlib import Path

from jev.contracts import Event, Operation, Outcome, Result
from jev.services.client import DecisionClient
from jev.services.paths import is_within
from jev.services.storage import Storage, operation_digest


POLICY_VERSION = "safety-v1"
FILE_TOOLS = {"write_to_file", "replace_file_content", "multi_replace_file_content", "apply_patch"}
SENSITIVE_MARKERS = (
    "/.ssh/", "/id_rsa", "/id_ed25519", "/.aws/credentials",
    "/etc/passwd", "/etc/shadow", "c:/windows/system32",
)
CRITICAL_PATTERNS = (
    (re.compile(r"(?i)\b(rmdir|rd|del|erase)\b.*(?:^|\s)/s(?:\s|$)"), "recursive_delete"),
    (re.compile(r"(?i)\brm\s+(?:-[a-z]*r[a-z]*f|-[a-z]*f[a-z]*r|--recursive)\b"), "recursive_delete"),
    (re.compile(r"(?i)\bgit\s+reset\s+--hard\b"), "git_hard_reset"),
    (re.compile(r"(?i)\bgit\s+clean\s+-[a-z]*f\b"), "git_force_clean"),
    (re.compile(r"(?i)\bgit\s+push\s+(?:.*\s)?(?:--force|-f)(?:\s|$)"), "git_force_push"),
    (re.compile(r"(?i)\bgit\s+(?:checkout\s+--\s+\.|restore\s+\.)"), "git_discard_all"),
    (re.compile(r"(?i)\b(?:format\s+[a-z]:|diskpart|fdisk|mkfs)\b"), "disk_destroy"),
    (re.compile(r"(?i)\b(?:curl|wget)\b.*\|\s*(?:bash|sh|powershell|pwsh|cmd)\b"), "remote_pipe_shell"),
    (re.compile(r"(?i)\b(?:DROP\s+(?:DATABASE|SCHEMA)|TRUNCATE\s+TABLE)\b"), "database_destroy"),
)


def clean_command(command: str) -> str:
    value = command.strip()
    for prefix in ("cmd.exe /c ", "cmd /c "):
        if value.lower().startswith(prefix):
            value = value[len(prefix):].strip()
            break
    return value.strip("\"'")


def critical_reason(command: str) -> str:
    value = clean_command(command)
    for pattern, reason in CRITICAL_PATTERNS:
        if pattern.search(value):
            return reason
    return ""


def _sensitive_path(path: str) -> bool:
    normalized = path.lower().replace("\\", "/")
    return any(marker in normalized for marker in SENSITIVE_MARKERS)


def evaluate(
    event: Event,
    operation: Operation,
    storage: Storage,
    client: DecisionClient | None,
    semantic_timeout: float,
) -> tuple[Result, int | None]:
    started = time.monotonic()
    digest = operation_digest(operation.tool_name, operation.command, operation.arguments)
    if operation.kind == "file_mutation":
        if not operation.paths:
            return Result(
                outcome=Outcome.DENY,
                reason="Jev could not determine the file mutation target.",
                reason_code="unknown_file_target",
                feature="safety",
                feature_version=POLICY_VERSION,
                duration_ms=(time.monotonic() - started) * 1000,
            ), None
        for raw_path in operation.paths:
            target = Path(raw_path)
            if not target.is_absolute():
                target = Path(event.cwd) / target
            if _sensitive_path(str(target)) or not is_within(target, event.cwd):
                return Result(
                    outcome=Outcome.NEEDS_CONFIRMATION,
                    reason="File mutation targets a sensitive path or leaves the workspace.",
                    reason_code="sensitive_or_external_path",
                    feature="safety",
                    feature_version=POLICY_VERSION,
                    duration_ms=(time.monotonic() - started) * 1000,
                ), None
        return Result(
            outcome=Outcome.ALLOW,
            reason_code="workspace_file_fast_path",
            feature="safety",
            feature_version=POLICY_VERSION,
            duration_ms=(time.monotonic() - started) * 1000,
        ), None

    reason_code = critical_reason(operation.command)
    if reason_code:
        return Result(
            outcome=Outcome.DENY,
            reason=f"Jev invariant blocked this operation ({reason_code}).",
            reason_code=reason_code,
            feature="safety",
            feature_version=POLICY_VERSION,
            duration_ms=(time.monotonic() - started) * 1000,
        ), None

    try:
        decision, reason, rule_id = storage.find_rule(
            harness=event.harness.value,
            workspace_id=event.workspace_id,
            session_id=event.session_id,
            tool_name=operation.tool_name,
            command=clean_command(operation.command),
            digest=digest,
        )
    except Exception:
        decision, reason, rule_id = "unknown", "", None
    if decision in {"allow", "deny"}:
        return Result(
            outcome=Outcome(decision),
            reason=reason,
            reason_code="trusted_rule",
            feature="safety",
            feature_version=POLICY_VERSION,
            source="rules",
            duration_ms=(time.monotonic() - started) * 1000,
        ), rule_id

    if client is None or not operation.command:
        return Result(
            outcome=Outcome.ALLOW,
            reason_code="deterministic_checks_passed",
            feature="safety",
            feature_version=POLICY_VERSION,
            duration_ms=(time.monotonic() - started) * 1000,
        ), None

    try:
        answers = client.evaluate(
            {"tool": operation.tool_name, "command": clean_command(operation.command)},
            {
                "routine": {"type": "noul", "instructions": "Is this a routine development action with a clear recovery path?"},
                "destructive": {"type": "noul", "instructions": "Could this action irreversibly destroy data or history?"},
            },
            semantic_timeout,
        )
        routine = float(answers.get("routine", {}).get("noul", 0.0))
        destructive = float(answers.get("destructive", {}).get("noul", 0.0))
        outcome = Outcome.NEEDS_CONFIRMATION if destructive >= 0.5 or (routine < 0.35 and destructive >= 0.35) else Outcome.ALLOW
        return Result(
            outcome=outcome,
            reason="Jev classified the operation as conditionally risky." if outcome == Outcome.NEEDS_CONFIRMATION else "",
            reason_code="semantic_risk" if outcome == Outcome.NEEDS_CONFIRMATION else "semantic_routine",
            data={"routine": routine, "destructive": destructive},
            feature="safety",
            feature_version=POLICY_VERSION,
            source="jev",
            duration_ms=(time.monotonic() - started) * 1000,
        ), None
    except Exception as exc:
        return Result(
            outcome=Outcome.ALLOW,
            reason_code="semantic_unavailable",
            feature="safety",
            feature_version=POLICY_VERSION,
            source="deterministic_fallback",
            duration_ms=(time.monotonic() - started) * 1000,
            error=type(exc).__name__,
        ), None
