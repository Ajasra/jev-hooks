from __future__ import annotations

from pathlib import Path

from jev.contracts import Outcome
from jev.core import knowledge, verification
from jev.services.paths import Settings
from jev.services.storage import Storage
from jev.tooling import record_gotcha as tool_record_gotcha
from jev.tooling import verify_completion as tool_verify_completion


def test_gotchas_root_is_automatic_knowledge_root(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    settings = Settings.load(tmp_path)
    expected_gotchas = (tmp_path / "docs" / "gotchas").resolve()
    assert expected_gotchas in settings.knowledge_roots


def test_record_and_search_gotcha(tmp_path: Path):
    gotchas_dir = tmp_path / "docs" / "gotchas"

    # 1. Record a gotcha
    res = knowledge.record_gotcha(
        title="Async sqlite3 lock contention",
        trap="Under heavy concurrency, SQLite throws OperationalError: database is locked if busy_timeout is low.",
        remediation="Set PRAGMA busy_timeout = 5000 and enable PRAGMA journal_mode = WAL.",
        root=gotchas_dir,
        tags=["sqlite", "concurrency", "wal"],
    )
    assert res["success"] is True
    assert (gotchas_dir / "async_sqlite3_lock_contention.md").exists()

    # 2. Load items
    items = knowledge.load_items((gotchas_dir,))
    assert len(items) == 1
    assert items[0]["provenance"] == "gotcha"
    assert items[0]["title"] == "Async sqlite3 lock contention"
    assert "concurrency" in items[0]["tags"]

    # 3. Search gotchas via keyword match
    search_res = knowledge.search("sqlite concurrency lock issue", (gotchas_dir,))
    assert search_res.data["selected"] == "gotcha_async_sqlite3_lock_contention"
    assert len(search_res.context) == 1
    assert "Operational Gotcha [Async sqlite3 lock contention]" in search_res.context[0].text
    assert "PRAGMA journal_mode = WAL" in search_res.context[0].text


def test_tool_record_gotcha(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    settings = Settings.load(tmp_path)
    res = tool_record_gotcha(
        settings=settings,
        title="Pydantic v2 json schema migration",
        trap="schema() method was replaced by model_json_schema().",
        remediation="Use model_json_schema() instead of schema().",
        tags=["pydantic", "v2"],
    )
    assert res["success"] is True
    assert (tmp_path / "docs" / "gotchas" / "pydantic_v2_json_schema_migration.md").exists()


def test_empirical_verification_missing_sections(tmp_path: Path):
    store = Storage(tmp_path / "test.sqlite3")
    store.initialize()

    # Claim missing LEARNINGS
    incomplete_claim = """
    ## 1. WHAT
    Added loop guard feature.

    ## 2. WHY
    To avoid agent stall loops.

    ## 3. HOW
    Ran tests.
    """
    res = verification.verify_completion_claim(incomplete_claim, "session_1", store)
    assert res["valid_schema"] is False
    assert res["missing_sections"] == ["LEARNINGS"]
    assert res["outcome"] == Outcome.NEEDS_CONFIRMATION
    assert res["reason_code"] == "missing_schema_sections"


def test_empirical_verification_unverified_test_claim(tmp_path: Path):
    store = Storage(tmp_path / "test.sqlite3")
    store.initialize()

    complete_claim = """
    ## 1. WHAT
    Added loop guard feature and three-tier safety rules.

    ## 2. WHY
    To avoid agent stall loops and prevent repository corruption.

    ## 3. HOW
    All 38 tests passed cleanly with pytest.

    ## 4. LEARNINGS
    Always configure SQLite WAL journal mode.
    """
    # No test tool was executed in session_1
    res = verification.verify_completion_claim(complete_claim, "session_1", store)
    assert res["valid_schema"] is True
    assert res["empirical_verified"] is False
    assert res["outcome"] == Outcome.NEEDS_CONFIRMATION
    assert res["reason_code"] == "unverified_claim"


def test_empirical_verification_successful_match(tmp_path: Path):
    store = Storage(tmp_path / "test.sqlite3")
    store.initialize()

    # Record a successful test execution
    store.record_tool_invocation(
        session_id="session_ok",
        workspace_id=str(tmp_path),
        tool_name="run_command",
        operation_digest="pytest_digest",
        command="pytest tests/",
        event_kind="tool.after",
        exit_code=0,
        status="success",
    )

    complete_claim = """
    ## 1. WHAT
    Added loop guard feature and three-tier safety rules.

    ## 2. WHY
    To avoid agent stall loops and prevent repository corruption.

    ## 3. HOW
    Ran pytest tests/ and all 38 tests passed cleanly.

    ## 4. LEARNINGS & ARCHITECTURAL GOTCHAS
    Always configure SQLite WAL journal mode.
    """
    res = verification.verify_completion_claim(complete_claim, "session_ok", store)
    assert res["valid_schema"] is True
    assert res["empirical_verified"] is True
    assert res["outcome"] == Outcome.ALLOW
    assert res["reason_code"] == "empirical_verification_passed"


def test_tool_verify_completion(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    settings = Settings.load(tmp_path)
    store = Storage(settings.db_path)
    store.initialize()

    # Claim without test assertions
    claim = """
    ## 1. WHAT
    Updated documentation.

    ## 2. WHY
    To clarify operational architecture.

    ## 3. HOW
    Wrote docs in docs/architecture.md.

    ## 4. LEARNINGS
    Clear documentation prevents confusion.
    """
    res = tool_verify_completion(settings, claim, "session_doc")
    assert res["valid_schema"] is True
    assert res["empirical_verified"] is True
    assert res["outcome"] == Outcome.ALLOW
