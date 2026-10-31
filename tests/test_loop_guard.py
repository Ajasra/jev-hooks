from __future__ import annotations

from pathlib import Path

from jev.contracts import Event, EventKind, Harness, Operation, Outcome
from jev.core import loop_guard
from jev.runtime import Runtime
from jev.services.paths import Settings
from jev.services.storage import Storage, operation_digest


def make_test_settings(tmp_path: Path) -> Settings:
    return Settings(
        workspace_root=tmp_path,
        package_root=tmp_path,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "data/cache",
        db_path=tmp_path / "data/jev.sqlite3",
        skill_roots=(tmp_path / ".agents/skills",),
        knowledge_roots=(tmp_path / ".agents/knowledge",),
        semantic_timeout_seconds=0.05,
    )


def test_circuit_breaker_trips_after_three_consecutive_failures(tmp_path: Path):
    store = Storage(tmp_path / "test.sqlite3")
    store.initialize()

    op = Operation(kind="command", tool_name="run_command", command="python fail.py", arguments={})
    event = Event(
        event_id="e1",
        harness=Harness.ANTIGRAVITY,
        workspace_id=str(tmp_path),
        session_id="session_123",
        kind=EventKind.TOOL_BEFORE,
        cwd=str(tmp_path),
    )

    # 1. First attempt: circuit breaker does not trip
    res = loop_guard.evaluate_before(event, op, store)
    assert res.outcome == Outcome.ABSTAIN

    # Record 1st failure
    after_event = Event(
        event_id="e1_after",
        harness=Harness.ANTIGRAVITY,
        workspace_id=str(tmp_path),
        session_id="session_123",
        kind=EventKind.TOOL_AFTER,
        cwd=str(tmp_path),
        payload={"exit_code": 1, "error": "AssertionError"},
    )
    loop_guard.record_after(after_event, op, store)

    # 2. Second attempt: fails = 1, circuit breaker does not trip
    res = loop_guard.evaluate_before(event, op, store)
    assert res.outcome == Outcome.ABSTAIN

    # Record 2nd failure
    loop_guard.record_after(after_event, op, store)

    # 3. Third attempt: fails = 2, circuit breaker does not trip yet
    res = loop_guard.evaluate_before(event, op, store)
    assert res.outcome == Outcome.ABSTAIN

    # Record 3rd failure
    loop_guard.record_after(after_event, op, store)

    # 4. Fourth attempt: fails = 3, circuit breaker TRIPS!
    res = loop_guard.evaluate_before(event, op, store)
    assert res.outcome == Outcome.DENY
    assert res.reason_code == "circuit_breaker_tripped"
    assert len(res.context) == 1
    assert "Circuit breaker tripped" in res.context[0].text
    assert "Review git diff" in res.context[0].text


def test_circuit_breaker_resets_on_success_or_different_action(tmp_path: Path):
    store = Storage(tmp_path / "test.sqlite3")
    store.initialize()

    op1 = Operation(kind="command", tool_name="run_command", command="python fail.py", arguments={})
    op2 = Operation(kind="command", tool_name="run_command", command="python other.py", arguments={})
    event = Event(
        event_id="e1",
        harness=Harness.ANTIGRAVITY,
        workspace_id=str(tmp_path),
        session_id="session_123",
        kind=EventKind.TOOL_BEFORE,
        cwd=str(tmp_path),
    )
    fail_after = Event(
        event_id="e1_after",
        harness=Harness.ANTIGRAVITY,
        workspace_id=str(tmp_path),
        session_id="session_123",
        kind=EventKind.TOOL_AFTER,
        cwd=str(tmp_path),
        payload={"exit_code": 1, "error": "Fail"},
    )

    # 2 failures on op1
    loop_guard.record_after(fail_after, op1, store)
    loop_guard.record_after(fail_after, op1, store)

    # Operation 2 runs and succeeds
    success_after = Event(
        event_id="e2_after",
        harness=Harness.ANTIGRAVITY,
        workspace_id=str(tmp_path),
        session_id="session_123",
        kind=EventKind.TOOL_AFTER,
        cwd=str(tmp_path),
        payload={"exit_code": 0},
    )
    loop_guard.record_after(success_after, op2, store)

    # op1 consecutive failure count is interrupted
    digest1 = operation_digest(op1.tool_name, op1.command, op1.arguments)
    assert store.get_consecutive_failures("session_123", digest1) == 0


def test_runtime_dispatch_trips_loop_guard(tmp_path: Path):
    cfg = make_test_settings(tmp_path)
    runtime = Runtime(cfg)

    op = Operation(kind="command", tool_name="run_command", command="build --target app", arguments={})
    before_event = Event(
        event_id="b1",
        harness=Harness.ANTIGRAVITY,
        workspace_id=str(tmp_path),
        session_id="sess_rt",
        kind=EventKind.TOOL_BEFORE,
        cwd=str(tmp_path),
    )
    after_event = Event(
        event_id="a1",
        harness=Harness.ANTIGRAVITY,
        workspace_id=str(tmp_path),
        session_id="sess_rt",
        kind=EventKind.TOOL_AFTER,
        cwd=str(tmp_path),
        payload={"exit_code": 2, "error": "Build failed"},
    )

    # 3 cycles of failed execution
    for _ in range(3):
        res_before = runtime.dispatch(before_event, op)
        assert res_before.outcome != Outcome.DENY
        runtime.dispatch(after_event, op)

    # 4th cycle should be denied by circuit breaker
    res_tripped = runtime.dispatch(before_event, op)
    assert res_tripped.outcome == Outcome.DENY
    assert res_tripped.reason_code == "circuit_breaker_tripped"
