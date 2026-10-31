"""Shared deterministic and semantic safety policy implementing three-tier boundaries."""

from __future__ import annotations

import re
import time
from pathlib import Path

from jev.contracts import Event, Operation, Outcome, Result
from jev.services.client import DecisionClient, failure_details
from jev.services.paths import is_within
from jev.services.storage import SECRET_PATTERN, Storage, operation_digest

POLICY_VERSION = "safety-v1"
FILE_TOOLS = {"write_to_file", "replace_file_content", "multi_replace_file_content", "apply_patch"}
SENSITIVE_MARKERS = (
    "/.ssh/", "/id_rsa", "/id_ed25519", "/.aws/credentials",
    "/etc/passwd", "/etc/shadow", "c:/windows/system32",
)

# NEVER Tier: Hard Invariants -> Outcome.DENY
CRITICAL_PATTERNS = (
    (re.compile(r"(?i)\b(rmdir|rd|del|erase)\b.*(?:^|\s)/s(?:\s|$)"), "recursive_delete"),
    (re.compile(r"(?i)\brm\s+(?:-[a-z]*r[a-z]*f|-[a-z]*f[a-z]*r|--recursive)\b"), "recursive_delete"),
    (re.compile(r"(?i)\bgit\s+reset\s+--hard\b"), "git_hard_reset"),
    (re.compile(r"(?i)\bgit\s+clean\s+-[a-z]*f[a-z]*\b"), "git_force_clean"),
    (re.compile(r"(?i)\bgit\s+push\s+(?:.*?\s)?(?:--force|-f)(?:\s|$)"), "git_force_push"),
    (re.compile(r"(?i)\b(?:format\s+[a-z]:|diskpart|fdisk|mkfs)\b"), "disk_destroy"),
    (re.compile(r"(?i)\b(?:curl|wget)\b.*\|\s*(?:bash|sh|powershell|pwsh|cmd)\b"), "remote_pipe_shell"),
    (re.compile(r"(?i)\bgit\s+(?:add|commit)\b.*(?:\.env|\bcredentials\b|\bid_rsa\b|\bid_ed25519\b)"), "secret_leak_prevention"),
)

BLANKET_SUPPRESSION_PATTERN = re.compile(
    r"(?i)(?:#\s*noqa(?!\s*:\s*[a-zA-Z0-9_-]+)|@ts-ignore|@ts-nocheck)"
)

# ASK FIRST Tier -> Outcome.NEEDS_CONFIRMATION
ASK_FIRST_PATTERNS = (
    (re.compile(r"(?i)\b(?:DROP\s+(?:DATABASE|SCHEMA|TABLE)|TRUNCATE\s+TABLE)\b"), "database_schema_drop"),
    (re.compile(r"(?i)\b(?:alembic\s+downgrade|prisma\s+migrate\s+reset|rails\s+db:drop)\b"), "database_schema_drop"),
    (re.compile(r"(?i)\b(?:pip[0-9.]*|poetry|uv|pipenv)\s+(?:install|add)\b"), "package_dependency_add"),
    (re.compile(r"(?i)\b(?:npm|yarn|pnpm|bun)\s+(?:install|i|add)\b"), "package_dependency_add"),
    (re.compile(r"(?i)\b(?:cargo\s+add|go\s+get)\b"), "package_dependency_add"),
    (re.compile(r"(?i)\b(?:git\s+rm|rm\s+-[a-z]*r(?![a-z]*f)\b)"), "destructive_deletion"),
    (re.compile(r"(?i)\bgit\s+(?:checkout\s+--\s+\.|restore\s+\.)"), "destructive_deletion"),
)

# ALWAYS Tier: Routine development commands -> Outcome.ALLOW
ALWAYS_PATTERNS = (
    (re.compile(r"(?i)\b(?:pytest|py\.test|unittest|vitest|jest)\b"), "local_test_fast_path"),
    (re.compile(r"(?i)\b(?:npm|yarn|pnpm|bun)\s+(?:test|run\s+test)\b"), "local_test_fast_path"),
    (re.compile(r"(?i)\b(?:cargo|go)\s+test\b"), "local_test_fast_path"),
    (re.compile(r"(?i)\bpython[0-9.]*\s+-m\s+(?:unittest|pytest)\b"), "local_test_fast_path"),
    (re.compile(r"(?i)\b(?:ruff|biome|eslint|prettier|black|flake8|mypy)\b"), "linter_formatter_fast_path"),
    (re.compile(r"(?i)\bcargo\s+(?:clippy|fmt)\b"), "linter_formatter_fast_path"),
    (re.compile(r"(?i)\bgit\s+(?:status|diff|log|show|branch)\b"), "git_inspect_fast_path"),
    (re.compile(r"(?i)\bgit\s+push\s+(?:\S+\s+)?(?:\S+:)?(?:main|master)\b"), "git_push_trunk_fast_path"),
)


def _is_trunk_branch(cwd: str) -> bool:
    target = Path(cwd)
    for p in (target, *target.parents):
        head = p / ".git" / "HEAD"
        if head.is_file():
            try:
                content = head.read_text(encoding="utf-8").strip()
                if content in ("ref: refs/heads/main", "ref: refs/heads/master"):
                    return True
                if content.startswith("ref: refs/heads/"):
                    return False
            except OSError:
                pass
            break
    return False


def clean_command(command: str) -> str:
    value = command.strip()
    for prefix in ("cmd.exe /c ", "cmd /c "):
        if value.lower().startswith(prefix):
            value = value[len(prefix):].strip()
            break
    return value.strip("\"'")


def critical_reason(command: str, cwd: str = "") -> str:
    value = clean_command(command)
    for pattern, reason in CRITICAL_PATTERNS:
        if pattern.search(value):
            return reason
    if BLANKET_SUPPRESSION_PATTERN.search(value):
        return "blanket_suppression"
    if re.search(r"(?i)\bgit\s+commit\b", value) and cwd and _is_trunk_branch(cwd):
        return "direct_trunk_commit"
    return ""


def ask_first_reason(command: str) -> str:
    value = clean_command(command)
    for pattern, reason in ASK_FIRST_PATTERNS:
        if pattern.search(value):
            return reason
    return ""


def always_reason(command: str) -> str:
    value = clean_command(command)
    for pattern, reason in ALWAYS_PATTERNS:
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

            if target.name == ".env" or str(target).endswith("/.env"):
                return Result(
                    outcome=Outcome.DENY,
                    reason="Jev invariant blocked mutating plaintext secrets/.env file.",
                    reason_code="secret_leak_prevention",
                    feature="safety",
                    feature_version=POLICY_VERSION,
                    duration_ms=(time.monotonic() - started) * 1000,
                ), None

            if _sensitive_path(str(target)) or not is_within(target, event.cwd):
                return Result(
                    outcome=Outcome.NEEDS_CONFIRMATION,
                    reason="File mutation targets a sensitive path or leaves the workspace.",
                    reason_code="sensitive_or_external_path",
                    feature="safety",
                    feature_version=POLICY_VERSION,
                    duration_ms=(time.monotonic() - started) * 1000,
                ), None

        for key in ("ReplacementContent", "replacement_content", "CodeContent", "code_content", "content", "command", "patch"):
            val = str(operation.arguments.get(key) or "")
            if val and BLANKET_SUPPRESSION_PATTERN.search(val):
                return Result(
                    outcome=Outcome.DENY,
                    reason="Jev invariant blocked blanket compiler or linter suppression (# noqa, @ts-ignore).",
                    reason_code="blanket_suppression",
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

    # NEVER Tier: Invariants
    reason_code = critical_reason(operation.command, event.cwd)
    if reason_code:
        return Result(
            outcome=Outcome.DENY,
            reason=f"Jev invariant blocked this operation ({reason_code}).",
            reason_code=reason_code,
            feature="safety",
            feature_version=POLICY_VERSION,
            duration_ms=(time.monotonic() - started) * 1000,
        ), None

    # ALWAYS Tier: Local tests, linters, read-only commands
    routine_code = always_reason(operation.command)
    if routine_code:
        return Result(
            outcome=Outcome.ALLOW,
            reason="Routine development action permitted.",
            reason_code=routine_code,
            feature="safety",
            feature_version=POLICY_VERSION,
            duration_ms=(time.monotonic() - started) * 1000,
        ), None

    # ASK FIRST Tier: Schema drop, package add, destructive deletion
    ask_code = ask_first_reason(operation.command)
    if ask_code:
        return Result(
            outcome=Outcome.NEEDS_CONFIRMATION,
            reason=f"Jev requires confirmation for sensitive action ({ask_code}).",
            reason_code=ask_code,
            feature="safety",
            feature_version=POLICY_VERSION,
            duration_ms=(time.monotonic() - started) * 1000,
        ), None

    # Storage rule evaluation
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
            data=failure_details(exc),
            timed_out=bool(failure_details(exc)["timed_out"]),
        ), None
