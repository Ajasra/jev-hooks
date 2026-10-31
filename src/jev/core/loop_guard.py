"""Runtime tool call loop detection and circuit breaker policy."""

from __future__ import annotations

from jev.contracts import ContextItem, Event, Operation, Outcome, Result
from jev.services.storage import Storage, operation_digest

CIRCUIT_BREAKER_THRESHOLD = 3
FEATURE_ID = "loop_guard"
VERSION = "1"


def evaluate_before(event: Event, operation: Operation | None, storage: Storage) -> Result:
    if operation is None or not operation.tool_name:
        return Result(outcome=Outcome.ABSTAIN, feature=FEATURE_ID, feature_version=VERSION)

    digest = operation_digest(operation.tool_name, operation.command, operation.arguments)
    consecutive_fails = storage.get_consecutive_failures(
        event.session_id, digest, workspace_id=event.workspace_id, harness=event.harness.value
    )

    if consecutive_fails >= CIRCUIT_BREAKER_THRESHOLD:
        instruction = (
            "Circuit breaker tripped: Identical action failed 3 times. "
            "Prohibit further syntax mutations. Review git diff, analyze error logs, and invoke diagnostic replanning."
        )
        return Result(
            outcome=Outcome.DENY,
            reason=f"Circuit breaker tripped: Identical action failed {consecutive_fails} times consecutively.",
            reason_code="circuit_breaker_tripped",
            context=[ContextItem(feature=FEATURE_ID, text=instruction, priority=95)],
            feature=FEATURE_ID,
            feature_version=VERSION,
            data={"consecutive_failures": consecutive_fails, "digest": digest},
        )
    return Result(outcome=Outcome.ABSTAIN, feature=FEATURE_ID, feature_version=VERSION)


def record_after(event: Event, operation: Operation | None, storage: Storage) -> Result:
    if operation is None or not operation.tool_name:
        return Result(outcome=Outcome.ABSTAIN, feature=FEATURE_ID, feature_version=VERSION)

    payload = event.payload
    exit_code = payload.get("exit_code")
    if exit_code is None:
        exit_code = payload.get("returncode")
    error = payload.get("error", "")

    tool_response = payload.get("tool_response")
    if isinstance(tool_response, dict):
        if exit_code is None:
            exit_code = tool_response.get("exit_code", tool_response.get("returncode"))
        if not error:
            error = tool_response.get("error", "")
    elif isinstance(tool_response, str) and not error:
        if exit_code is not None and exit_code != 0:
            error = tool_response[:200]

    is_failure = bool(error) or (exit_code is not None and exit_code != 0)
    status = "failure" if is_failure else "success" if exit_code == 0 else "unknown"

    storage.record_tool_invocation(
        event=event,
        operation=operation,
        status=status,
        exit_code=exit_code,
        error=str(error),
    )
    return Result(outcome=Outcome.ABSTAIN, feature=FEATURE_ID, feature_version=VERSION,
                  reason_code="tool_result_recorded", data={"tool_status": status, "exit_code": exit_code})
