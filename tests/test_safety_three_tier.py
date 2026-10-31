from __future__ import annotations

from pathlib import Path

from jev.contracts import Event, EventKind, Harness, Operation, Outcome
from jev.core import safety
from jev.services.storage import Storage


def make_event(tmp_path: Path, session_id: str = "s1") -> Event:
    return Event(
        event_id="evt_test",
        harness=Harness.ANTIGRAVITY,
        workspace_id=str(tmp_path),
        session_id=session_id,
        kind=EventKind.TOOL_BEFORE,
        cwd=str(tmp_path),
    )


# --- NEVER TIER TESTS ---

def test_never_tier_git_force_push_and_reset(tmp_path: Path):
    store = Storage(tmp_path / "test.sqlite3")
    event = make_event(tmp_path)

    for cmd, expected_code in [
        ("git push --force origin feat", "git_force_push"),
        ("git push -f origin main", "git_force_push"),
        ("git reset --hard HEAD~1", "git_hard_reset"),
        ("git clean -fd", "git_force_clean"),
        ("rm -rf src/", "recursive_delete"),
    ]:
        op = Operation(kind="command", tool_name="run_command", command=cmd, arguments={})
        res, _ = safety.evaluate(event, op, store, None, 0.1)
        assert res.outcome == Outcome.DENY
        assert res.reason_code == expected_code


def test_never_tier_secret_leak_and_env_commit(tmp_path: Path):
    store = Storage(tmp_path / "test.sqlite3")
    event = make_event(tmp_path)

    op_cmd = Operation(kind="command", tool_name="run_command", command="git add .env", arguments={})
    res, _ = safety.evaluate(event, op_cmd, store, None, 0.1)
    assert res.outcome == Outcome.DENY
    assert res.reason_code == "secret_leak_prevention"

    op_file = Operation(
        kind="file_mutation",
        tool_name="write_to_file",
        arguments={"TargetFile": ".env", "CodeContent": "API_KEY=123"},
        paths=(".env",),
    )
    res_file, _ = safety.evaluate(event, op_file, store, None, 0.1)
    assert res_file.outcome == Outcome.DENY
    assert res_file.reason_code == "secret_leak_prevention"


def test_never_tier_blanket_suppression(tmp_path: Path):
    store = Storage(tmp_path / "test.sqlite3")
    event = make_event(tmp_path)

    # In file content
    op_file = Operation(
        kind="file_mutation",
        tool_name="replace_file_content",
        arguments={"TargetFile": "src/app.py", "ReplacementContent": "x = 1  # noqa\n"},
        paths=("src/app.py",),
    )
    res, _ = safety.evaluate(event, op_file, store, None, 0.1)
    assert res.outcome == Outcome.DENY
    assert res.reason_code == "blanket_suppression"

    # Specific noqa with code is allowed
    op_file_specific = Operation(
        kind="file_mutation",
        tool_name="replace_file_content",
        arguments={"TargetFile": "src/app.py", "ReplacementContent": "x = 1  # noqa: F401\n"},
        paths=("src/app.py",),
    )
    res_spec, _ = safety.evaluate(event, op_file_specific, store, None, 0.1)
    assert res_spec.outcome == Outcome.ALLOW


def test_never_tier_direct_trunk_commit(tmp_path: Path):
    store = Storage(tmp_path / "test.sqlite3")
    # Simulate git repo on main branch
    git_dir = tmp_path / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

    event = make_event(tmp_path)
    op = Operation(kind="command", tool_name="run_command", command='git commit -m "fix"', arguments={})
    res, _ = safety.evaluate(event, op, store, None, 0.1)
    assert res.outcome == Outcome.DENY
    assert res.reason_code == "direct_trunk_commit"


# --- ASK FIRST TIER TESTS ---

def test_ask_first_tier_database_drops_and_package_installs(tmp_path: Path):
    store = Storage(tmp_path / "test.sqlite3")
    event = make_event(tmp_path)

    for cmd, expected_code in [
        ("DROP DATABASE production;", "database_schema_drop"),
        ("TRUNCATE TABLE users;", "database_schema_drop"),
        ("alembic downgrade -1", "database_schema_drop"),
        ("pip install requests", "package_dependency_add"),
        ("npm install lodash", "package_dependency_add"),
        ("cargo add serde", "package_dependency_add"),
        ("git rm old_module.py", "destructive_deletion"),
        ("git restore .", "destructive_deletion"),
    ]:
        op = Operation(kind="command", tool_name="run_command", command=cmd, arguments={})
        res, _ = safety.evaluate(event, op, store, None, 0.1)
        assert res.outcome == Outcome.NEEDS_CONFIRMATION
        assert res.reason_code == expected_code


def test_ask_first_tier_external_path(tmp_path: Path):
    store = Storage(tmp_path / "test.sqlite3")
    event = make_event(tmp_path)

    op_ext = Operation(
        kind="file_mutation",
        tool_name="write_to_file",
        arguments={"TargetFile": "/etc/hosts", "CodeContent": "127.0.0.1 bad"},
        paths=("/etc/hosts",),
    )
    res, _ = safety.evaluate(event, op_ext, store, None, 0.1)
    assert res.outcome == Outcome.NEEDS_CONFIRMATION
    assert res.reason_code == "sensitive_or_external_path"


# --- ALWAYS TIER TESTS ---

def test_always_tier_routine_actions(tmp_path: Path):
    store = Storage(tmp_path / "test.sqlite3")
    event = make_event(tmp_path)

    for cmd, expected_code in [
        ("pytest tests/", "local_test_fast_path"),
        ("npm test", "local_test_fast_path"),
        ("cargo test", "local_test_fast_path"),
        ("python -m unittest discover", "local_test_fast_path"),
        ("ruff check .", "linter_formatter_fast_path"),
        ("biome check src/", "linter_formatter_fast_path"),
        ("git status", "git_inspect_fast_path"),
        ("git diff", "git_inspect_fast_path"),
    ]:
        op = Operation(kind="command", tool_name="run_command", command=cmd, arguments={})
        res, _ = safety.evaluate(event, op, store, None, 0.1)
        assert res.outcome == Outcome.ALLOW
        assert res.reason_code == expected_code

    # Safe workspace file mutation
    op_edit = Operation(
        kind="file_mutation",
        tool_name="write_to_file",
        arguments={"TargetFile": "src/utils.py", "CodeContent": "def add(a, b): return a + b\n"},
        paths=("src/utils.py",),
    )
    res_edit, _ = safety.evaluate(event, op_edit, store, None, 0.1)
    assert res_edit.outcome == Outcome.ALLOW
    assert res_edit.reason_code == "workspace_file_fast_path"
