from __future__ import annotations

import json
import subprocess
from pathlib import Path

from jev.core.semantic_lint import evaluate, load_rules
from jev.services.storage import Storage


class ViolationClient:
    def evaluate(self, state, questions, timeout):
        return {name: {"noul": 0.91} for name in questions}


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)


def test_ki_style_rule_evaluation_tracks_decision_and_harness_presentation(tmp_path: Path):
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    source = tmp_path / "src/jev/adapters/codex.py"
    source.parent.mkdir(parents=True)
    source.write_text("BASE = True\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    source.write_text("BASE = True\nFEATURE_LOGIC = True\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    root = tmp_path / ".agents/lint-rules/lr_shared"
    root.mkdir(parents=True)
    (root / "metadata.json").write_text(json.dumps({
        "id": "lr_shared", "version": 1, "title": "Shared boundary", "mode": "advisory",
        "level": "error", "question": "Is feature logic in an adapter?", "review_threshold": 0.6,
        "violation_threshold": 0.82, "include": ["src/jev/**/*.py"], "exclude": []
    }), encoding="utf-8")
    store = Storage(tmp_path / "data/jev.sqlite3")
    report = evaluate(workspace=tmp_path, roots=(root.parent,), storage=store,
                      client=ViolationClient(), harness="antigravity", workspace_id="workspace")
    assert report["findings"][0]["presentation"] == "prompt_user"
    assert report["findings"][0]["classification"] == "violation"
    decision_id = report["findings"][0]["decision_id"]
    store.record_semantic_lint_feedback(decision_id, "confirmed_violation")
    stats = store.semantic_lint_stats("lr_shared")["rules"][0]
    assert stats["confirmed"] == 1

    codex_report = evaluate(workspace=tmp_path, roots=(root.parent,), storage=store,
                            client=ViolationClient(), harness="codex", workspace_id="workspace")
    assert codex_report["findings"][0]["presentation"] == "warn_user"


def test_observe_rule_is_logged_without_limiting_model(tmp_path: Path, monkeypatch):
    root = tmp_path / ".agents/lint-rules/lr_observe"
    root.mkdir(parents=True)
    (root / "metadata.json").write_text(json.dumps({
        "id": "lr_observe", "version": 1, "title": "Observe", "mode": "observe",
        "level": "warning", "question": "Is this questionable?", "include": ["**/*"]
    }), encoding="utf-8")
    monkeypatch.setattr("jev.core.semantic_lint.collect_diff", lambda *args, **kwargs: (
        "diff --git a/a.py b/a.py\n+++ b/a.py\n@@ -0,0 +1,1 @@\n+x = 1", False))
    store = Storage(tmp_path / "jev.sqlite3")
    report = evaluate(workspace=tmp_path, roots=(root.parent,), storage=store,
                      client=ViolationClient(), harness="codex", workspace_id="workspace")
    assert report["findings"] == []
    with store.connect() as connection:
        assert connection.execute("SELECT classification FROM semantic_lint_decisions").fetchone()[0] == "violation"


def test_invalid_rule_thresholds_are_rejected(tmp_path: Path):
    root = tmp_path / "lr_bad"
    root.mkdir()
    (root / "metadata.json").write_text(json.dumps({
        "id": "bad", "question": "Bad?", "review_threshold": 0.9, "violation_threshold": 0.2
    }), encoding="utf-8")
    try:
        load_rules((tmp_path,))
    except ValueError as exc:
        assert "bad" in str(exc)
    else:
        raise AssertionError("invalid thresholds were accepted")


def test_missing_provider_is_reported_without_false_pass(tmp_path: Path, monkeypatch):
    root = tmp_path / ".agents/lint-rules/lr_rule"
    root.mkdir(parents=True)
    (root / "metadata.json").write_text(json.dumps({
        "id": "lr_rule", "question": "Violation?", "include": ["**/*"]
    }), encoding="utf-8")
    monkeypatch.setattr("jev.core.semantic_lint.collect_diff", lambda *args, **kwargs: (
        "diff --git a/a.py b/a.py\n+++ b/a.py\n@@ -0,0 +1,1 @@\n+x = 1", False))
    report = evaluate(workspace=tmp_path, roots=(root.parent,), storage=Storage(tmp_path / "jev.sqlite3"),
                      client=None, harness="codex", workspace_id="workspace")
    assert report["status"] == "unavailable"
    assert report["findings"] == []
