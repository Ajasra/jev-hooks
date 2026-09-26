"""Harness-aware SQLite persistence for policy, audit, and idempotency."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from jev.contracts import Event, Outcome, Result


SCHEMA_VERSION = 1
SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|authorization|token|password|secret)(\s*[:=]\s*)([^\s,;]+)"
)


def redact(value: str, limit: int = 500) -> str:
    return SECRET_PATTERN.sub(r"\1\2[REDACTED]", value)[:limit]


def operation_digest(tool_name: str, command: str, arguments: Any) -> str:
    payload = json.dumps(
        {"tool": tool_name, "command": command, "arguments": arguments},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Claim:
    status: str
    result: Result | None = None


class Storage:
    def __init__(self, path: Path):
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.path), timeout=0.25)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        if not str(self.path).startswith("\\\\"):
            connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=250")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    migration_id TEXT NOT NULL UNIQUE,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    harness TEXT NOT NULL,
                    harness_version TEXT NOT NULL DEFAULT '',
                    workspace_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL DEFAULT '',
                    turn_id TEXT NOT NULL DEFAULT '',
                    tool_call_id TEXT NOT NULL DEFAULT '',
                    feature TEXT NOT NULL,
                    feature_version TEXT NOT NULL DEFAULT '',
                    phase TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    reason_code TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    duration_ms REAL NOT NULL DEFAULT 0,
                    timed_out INTEGER NOT NULL DEFAULT 0,
                    error TEXT NOT NULL DEFAULT '',
                    details TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS events_harness_time
                    ON events(harness, workspace_id, created_at);
                CREATE INDEX IF NOT EXISTS events_session
                    ON events(harness, workspace_id, session_id, turn_id);
                CREATE TABLE IF NOT EXISTS rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern TEXT NOT NULL,
                    tool_name TEXT NOT NULL DEFAULT '*',
                    scope TEXT NOT NULL CHECK(scope IN ('always', 'session', 'single_use')),
                    harness TEXT NOT NULL,
                    workspace_id TEXT NOT NULL DEFAULT '',
                    session_id TEXT NOT NULL DEFAULT '',
                    operation_digest TEXT NOT NULL DEFAULT '',
                    decision TEXT NOT NULL CHECK(decision IN ('allow', 'deny')),
                    provenance TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    expires_at TEXT,
                    consumed_at TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(pattern, tool_name, scope, harness, workspace_id, session_id, operation_digest)
                );
                CREATE TABLE IF NOT EXISTS invocations (
                    claim_key TEXT PRIMARY KEY,
                    harness TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    invocation_id TEXT NOT NULL,
                    feature TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    operation_digest TEXT NOT NULL,
                    policy_version TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('active', 'complete')),
                    lease_expires_at REAL NOT NULL,
                    result_json TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS session_context (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    harness TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL,
                    content TEXT NOT NULL,
                    freshness TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(harness, workspace_id, session_id, agent_id, source)
                );
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    harness TEXT NOT NULL,
                    label TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE VIEW IF NOT EXISTS codex_events AS
                    SELECT * FROM events WHERE harness = 'codex';
                CREATE VIEW IF NOT EXISTS antigravity_events AS
                    SELECT * FROM events WHERE harness = 'antigravity';
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, migration_id) VALUES (?, ?)",
                (SCHEMA_VERSION, "shared-harness-runtime-v1"),
            )

    def record_event(self, event: Event, result: Result) -> None:
        self.initialize()
        details = redact(json.dumps(result.data, sort_keys=True, default=str))
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO events(
                    event_id, harness, harness_version, workspace_id, session_id,
                    agent_id, turn_id, tool_call_id, feature, feature_version, phase,
                    outcome, reason_code, source, duration_ms, timed_out, error, details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.event_id,
                    event.harness.value,
                    event.harness_version,
                    event.workspace_id,
                    event.session_id,
                    event.agent_id,
                    event.turn_id,
                    event.tool_call_id,
                    result.feature,
                    result.feature_version,
                    event.kind.value,
                    result.outcome.value,
                    result.reason_code,
                    result.source,
                    result.duration_ms,
                    int(result.timed_out),
                    redact(result.error),
                    details,
                ),
            )

    def find_rule(
        self,
        *,
        harness: str,
        workspace_id: str,
        session_id: str,
        tool_name: str,
        command: str,
        digest: str,
    ) -> tuple[str, str, int | None]:
        self.initialize()
        now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM rules
                   WHERE harness IN (?, '*')
                     AND (workspace_id = '' OR workspace_id = ?)
                     AND (tool_name = '*' OR tool_name = ?)
                     AND (expires_at IS NULL OR expires_at > ?)
                     AND consumed_at IS NULL
                     AND (scope = 'always' OR (scope = 'session' AND session_id = ?)
                          OR (scope = 'single_use' AND operation_digest = ?))
                   ORDER BY CASE scope WHEN 'single_use' THEN 3 WHEN 'session' THEN 2 ELSE 1 END DESC,
                            id DESC""",
                (harness, workspace_id, tool_name, now, session_id, digest),
            ).fetchall()
            for row in rows:
                pattern = str(row["pattern"])
                if pattern == "*" or fnmatch.fnmatch(command.lower(), pattern.lower()):
                    consumable_id = int(row["id"]) if row["scope"] == "single_use" else None
                    return str(row["decision"]), str(row["reason"]), consumable_id
        return "unknown", "", None

    def consume_rule(self, rule_id: int | None) -> None:
        if rule_id is None:
            return
        with self.connect() as connection:
            connection.execute(
                "UPDATE rules SET consumed_at=CURRENT_TIMESTAMP WHERE id=? AND scope='single_use' AND consumed_at IS NULL",
                (rule_id,),
            )

    def save_rule(
        self,
        *,
        pattern: str,
        tool_name: str,
        scope: str,
        harness: str,
        workspace_id: str,
        session_id: str,
        digest: str,
        decision: str,
        provenance: str,
        reason: str = "",
        expires_at: str | None = None,
    ) -> None:
        self.initialize()
        if provenance not in {"manual_cli", "verified_native_receipt", "legacy_antigravity"}:
            raise ValueError("Untrusted rule provenance")
        with self.connect() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO rules(
                    pattern, tool_name, scope, harness, workspace_id, session_id,
                    operation_digest, decision, provenance, reason, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (pattern, tool_name, scope, harness, workspace_id, session_id, digest,
                 decision, provenance, reason, expires_at),
            )

    def _claim_key(self, event: Event, feature: str, phase: str) -> str:
        values = (
            event.harness.value,
            event.workspace_id,
            event.session_id,
            event.agent_id,
            event.invocation_id or event.event_id,
            feature,
            phase,
        )
        return hashlib.sha256("\x1f".join(values).encode("utf-8")).hexdigest()

    def claim(
        self,
        event: Event,
        feature: str,
        phase: str,
        digest: str,
        policy_version: str,
        lease_seconds: float = 10.0,
    ) -> Claim:
        self.initialize()
        key = self._claim_key(event, feature, phase)
        now = time.time()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM invocations WHERE claim_key=?", (key,)
            ).fetchone()
            if row and row["operation_digest"] == digest and row["policy_version"] == policy_version:
                if row["status"] == "complete" and row["result_json"]:
                    return Claim("replay", Result.from_dict(json.loads(row["result_json"])))
                if float(row["lease_expires_at"]) > now:
                    return Claim("active")
            connection.execute(
                """INSERT OR REPLACE INTO invocations(
                    claim_key, harness, workspace_id, session_id, invocation_id, feature,
                    phase, operation_digest, policy_version, status, lease_expires_at, result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, NULL)""",
                (key, event.harness.value, event.workspace_id, event.session_id,
                 event.invocation_id or event.event_id, feature, phase, digest,
                 policy_version, now + lease_seconds),
            )
            return Claim("acquired")

    def complete_claim(
        self,
        event: Event,
        feature: str,
        phase: str,
        result: Result,
        rule_id_to_consume: int | None = None,
    ) -> Result:
        key = self._claim_key(event, feature, phase)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if rule_id_to_consume is not None:
                consumed = connection.execute(
                    "UPDATE rules SET consumed_at=CURRENT_TIMESTAMP WHERE id=? AND scope='single_use' AND consumed_at IS NULL",
                    (rule_id_to_consume,),
                ).rowcount
                if consumed != 1:
                    result = Result(
                        outcome=Outcome.DENY,
                        reason="The one-use authorization was already consumed; request a new authorization.",
                        reason_code="authorization_already_consumed",
                        feature="safety",
                        feature_version=result.feature_version,
                        source="rules",
                    )
            connection.execute(
                """UPDATE invocations SET status='complete', result_json=?,
                   lease_expires_at=0, updated_at=CURRENT_TIMESTAMP WHERE claim_key=?""",
                (json.dumps(result.to_dict(), sort_keys=True), key),
            )
        return result

    def events(self, harness: str | None = None) -> list[dict[str, Any]]:
        self.initialize()
        with self.connect() as connection:
            if harness:
                rows = connection.execute(
                    "SELECT * FROM events WHERE harness=? ORDER BY id", (harness,)
                ).fetchall()
            else:
                rows = connection.execute("SELECT * FROM events ORDER BY id").fetchall()
            return [dict(row) for row in rows]

    def backup_to(self, target: Path) -> None:
        self.initialize()
        target.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as source, sqlite3.connect(str(target)) as destination:
            source.backup(destination)

    @staticmethod
    def backup_existing(source_path: Path, target: Path) -> None:
        """Back up an existing SQLite database without initializing or mutating it."""
        target.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(f"file:{source_path.resolve().as_posix()}?mode=ro", uri=True) as source:
            with sqlite3.connect(str(target)) as destination:
                source.backup(destination)

    def import_legacy(self, legacy_path: Path) -> int:
        """Import legacy rules as Antigravity-only records without widening scope."""
        if not legacy_path.exists():
            return 0
        self.initialize()
        imported = 0
        legacy = sqlite3.connect(str(legacy_path))
        legacy.row_factory = sqlite3.Row
        try:
            rows: Iterable[sqlite3.Row] = legacy.execute("SELECT * FROM rules").fetchall()
            for row in rows:
                self.save_rule(
                    pattern=str(row["pattern"]),
                    tool_name=str(row["tool_name"]),
                    scope=str(row["scope"]),
                    harness="antigravity",
                    workspace_id=str(row["workspace_path"] or ""),
                    session_id=str(row["conversation_id"] or ""),
                    digest="",
                    decision=str(row["decision"]),
                    provenance="legacy_antigravity",
                    reason=str(row["reason"] or ""),
                )
                imported += 1
        finally:
            legacy.close()
        return imported
