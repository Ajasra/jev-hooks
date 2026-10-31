"""Harness-aware SQLite persistence for policy, audit, and idempotency."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import sqlite3
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from jev.contracts import Event, Operation, Outcome, Result

SCHEMA_VERSION = 5
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


jev_operation_digest = operation_digest


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

    def connect_readonly(self) -> sqlite3.Connection:
        """Open the existing audit database without initializing or modifying it."""
        resolved = self.path.resolve()
        path = resolved.as_posix()
        if resolved.drive:
            path = "/" + path
        uri = f"file:{quote(path, safe='/:')}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=0.25)
        connection.row_factory = sqlite3.Row
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
                CREATE TABLE IF NOT EXISTS semantic_lint_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    harness TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    rule_id TEXT NOT NULL,
                    rule_version INTEGER NOT NULL,
                    rule_digest TEXT NOT NULL,
                    diff_digest TEXT NOT NULL,
                    path TEXT NOT NULL,
                    hunk_start INTEGER NOT NULL DEFAULT 0,
                    hunk_end INTEGER NOT NULL DEFAULT 0,
                    probability REAL NOT NULL,
                    classification TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    duration_ms REAL NOT NULL DEFAULT 0,
                    redacted INTEGER NOT NULL DEFAULT 0,
                    truncated INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS semantic_lint_rule_time
                    ON semantic_lint_decisions(rule_id, rule_version, created_at);
                CREATE TABLE IF NOT EXISTS semantic_lint_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    decision_id INTEGER NOT NULL REFERENCES semantic_lint_decisions(id),
                    label TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'user',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS verification_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    harness TEXT NOT NULL,
                    target_path TEXT NOT NULL DEFAULT '',
                    code_snippet TEXT NOT NULL DEFAULT '',
                    method_supported REAL NOT NULL DEFAULT 0.5,
                    arguments_match REAL NOT NULL DEFAULT 0.5,
                    support_level TEXT NOT NULL DEFAULT 'extrapolated',
                    advisory_emitted INTEGER NOT NULL DEFAULT 0,
                    duration_ms REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS verification_session_time
                    ON verification_decisions(session_id, created_at);
                CREATE TABLE IF NOT EXISTS knowledge_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL DEFAULT '',
                    session_id TEXT NOT NULL DEFAULT '',
                    harness TEXT NOT NULL DEFAULT '',
                    action TEXT NOT NULL,
                    target_ki TEXT NOT NULL DEFAULT '',
                    is_update INTEGER NOT NULL DEFAULT 0,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    summary TEXT NOT NULL DEFAULT '',
                    duration_ms REAL NOT NULL DEFAULT 0.0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS knowledge_session_time
                    ON knowledge_decisions(session_id, created_at);
                CREATE TABLE IF NOT EXISTS tool_invocations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    harness TEXT NOT NULL DEFAULT '',
                    tool_name TEXT NOT NULL,
                    operation_digest TEXT NOT NULL,
                    command TEXT,
                    event_kind TEXT NOT NULL,
                    exit_code INTEGER,
                    status TEXT NOT NULL,
                    error_summary TEXT,
                    created_at REAL NOT NULL,
                    timestamp REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tool_invocations_session
                    ON tool_invocations(session_id, workspace_id, operation_digest);
                CREATE VIEW IF NOT EXISTS codex_events AS
                    SELECT * FROM events WHERE harness = 'codex';
                CREATE VIEW IF NOT EXISTS antigravity_events AS
                    SELECT * FROM events WHERE harness = 'antigravity';
                CREATE VIEW IF NOT EXISTS opencode_events AS
                    SELECT * FROM events WHERE harness = 'opencode';
                """
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(tool_invocations)")}
            if "harness" not in columns:
                connection.execute("ALTER TABLE tool_invocations ADD COLUMN harness TEXT NOT NULL DEFAULT ''")
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, migration_id) VALUES (?, ?)",
                (5, "tool-invocations-harness-v5"),
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, migration_id) VALUES (?, ?)",
                (1, "shared-harness-runtime-v1"),
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, migration_id) VALUES (?, ?)",
                (2, "semantic-lint-v2"),
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, migration_id) VALUES (?, ?)",
                (3, "verification-v3"),
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, migration_id) VALUES (?, ?)",
                (4, "loop-guard-tool-invocations-v4"),
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, migration_id) VALUES (?, ?)",
                (SCHEMA_VERSION, "knowledge-lifecycle-v5"),
            )

    def record_tool_invocation(
        self,
        event: Event | None = None,
        operation: Operation | None = None,
        status: str = "pending",
        exit_code: int | None = None,
        error: str = "",
        session_id: str | None = None,
        workspace_id: str | None = None,
        tool_name: str | None = None,
        op_digest: str | None = None,
        operation_digest: str | None = None,
        command: str | None = None,
        event_kind: str | None = None,
    ) -> None:
        self.initialize()
        now = time.time()
        sess_id = session_id or (event.session_id if event else "")
        ws_id = workspace_id or (event.workspace_id if event else "")
        t_name = tool_name or (operation.tool_name if operation else "")
        cmd = command or (operation.command if operation else "")
        dig = op_digest or operation_digest
        if not dig and operation:
            dig = jev_operation_digest(operation.tool_name, operation.command, operation.arguments)
        e_kind = event_kind or (event.kind.value if event else "tool.after")
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO tool_invocations (
                    session_id, workspace_id, harness, tool_name, operation_digest,
                    command, event_kind, exit_code, status, error_summary,
                    created_at, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sess_id,
                    ws_id,
                    event.harness.value if event else "",
                    t_name,
                    dig or "",
                    cmd,
                    e_kind,
                    exit_code,
                    status,
                    redact(error) if error else "",
                    now,
                    now,
                ),
            )

    def update_tool_invocation(
        self,
        session_id: str,
        digest: str,
        status: str,
        exit_code: int | None = None,
        error: str = "",
    ) -> None:
        self.initialize()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE tool_invocations
                SET status = ?, exit_code = ?, error_summary = ?
                WHERE id = (
                    SELECT id FROM tool_invocations
                    WHERE session_id = ? AND operation_digest = ?
                    ORDER BY id DESC LIMIT 1
                )
                """,
                (status, exit_code, redact(error) if error else "", session_id, digest),
            )

    def get_consecutive_failures(
        self, session_id: str, digest: str, *, workspace_id: str | None = None, harness: str | None = None
    ) -> int:
        self.initialize()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                SELECT operation_digest, status, exit_code
                FROM tool_invocations
                WHERE session_id = ?
                  AND (? IS NULL OR workspace_id = ?)
                  AND (? IS NULL OR harness = ?)
                ORDER BY id DESC
                """,
                (session_id, workspace_id, workspace_id, harness, harness),
            )
            count = 0
            for row in cursor.fetchall():
                row_digest = row["operation_digest"]
                status = row["status"]
                exit_code = row["exit_code"]
                if row_digest != digest:
                    break
                is_failure = (status == "failure") or (exit_code is not None and exit_code != 0)
                if is_failure:
                    count += 1
                else:
                    break
            return count

    def get_successful_tool_invocations(self, session_id: str) -> list[dict[str, Any]]:
        self.initialize()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                SELECT tool_name, command, exit_code, status, created_at
                FROM tool_invocations
                WHERE session_id = ? AND status = 'success'
                ORDER BY id ASC
                """,
                (session_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def record_semantic_lint_decision(self, decision: dict[str, Any]) -> int:
        self.initialize()
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO semantic_lint_decisions(
                    event_id, harness, workspace_id, rule_id, rule_version, rule_digest,
                    diff_digest, path, hunk_start, hunk_end, probability, classification,
                    mode, duration_ms, redacted, truncated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                tuple(decision[key] for key in (
                    "event_id", "harness", "workspace_id", "rule_id", "rule_version",
                    "rule_digest", "diff_digest", "path", "hunk_start", "hunk_end",
                    "probability", "classification", "mode", "duration_ms", "redacted",
                    "truncated",
                )),
            )
            return int(cursor.lastrowid)

    def record_verification_decision(self, decision: Mapping[str, Any]) -> int:
        self.initialize()
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO verification_decisions(
                    event_id, session_id, harness, target_path, code_snippet,
                    method_supported, arguments_match, support_level,
                    advisory_emitted, duration_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(decision.get("event_id", "")),
                    str(decision.get("session_id", "")),
                    str(decision.get("harness", "")),
                    str(decision.get("target_path", "")),
                    str(decision.get("code_snippet", "")),
                    float(decision.get("method_supported", 0.5)),
                    float(decision.get("arguments_match", 0.5)),
                    str(decision.get("support_level", "extrapolated")),
                    int(decision.get("advisory_emitted", 0)),
                    float(decision.get("duration_ms", 0.0)),
                ),
            )
            return int(cursor.lastrowid or 0)

    def record_knowledge_decision(self, decision: Mapping[str, Any]) -> int:
        self.initialize()
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO knowledge_decisions(
                    event_id, session_id, harness, action, target_ki,
                    is_update, confidence, summary, duration_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(decision.get("event_id", "")),
                    str(decision.get("session_id", "")),
                    str(decision.get("harness", "")),
                    str(decision.get("action", "")),
                    str(decision.get("target_ki", "")),
                    1 if decision.get("is_update") else 0,
                    float(decision.get("confidence", 0.0)),
                    redact(str(decision.get("summary", "")), 400),
                    float(decision.get("duration_ms", 0.0)),
                ),
            )
            return int(cursor.lastrowid or 0)

    def record_semantic_lint_feedback(self, decision_id: int, label: str, reason: str = "") -> None:
        allowed = {"confirmed_violation", "false_positive", "missed_violation", "acceptable_exception", "rule_unclear", "fixed", "dismissed"}
        if label not in allowed:
            raise ValueError(f"Unsupported semantic lint feedback label: {label}")
        self.initialize()
        with self.connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM semantic_lint_decisions WHERE id=?", (decision_id,)
            ).fetchone()
            if not exists:
                raise ValueError(f"Unknown semantic lint decision: {decision_id}")
            connection.execute(
                "INSERT INTO semantic_lint_feedback(decision_id, label, reason) VALUES (?, ?, ?)",
                (decision_id, label, redact(reason)),
            )

    def knowledge_decision_stats(self) -> dict[str, Any]:
        self.initialize()
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT action, is_update, COUNT(*) as count,
                    ROUND(AVG(confidence), 3) as avg_confidence,
                    ROUND(AVG(duration_ms), 1) as avg_duration_ms
                    FROM knowledge_decisions
                    GROUP BY action, is_update"""
            ).fetchall()
            recent = connection.execute(
                """SELECT id, target_ki, is_update, confidence, summary, duration_ms, created_at
                    FROM knowledge_decisions ORDER BY id DESC LIMIT 20"""
            ).fetchall()
            return {
                "summary": [dict(r) for r in rows],
                "recent": [dict(r) for r in recent],
            }

    def semantic_lint_stats(self, rule_id: str | None = None) -> dict[str, Any]:
        self.initialize()
        where = "WHERE d.rule_id=?" if rule_id else ""
        params: tuple[Any, ...] = (rule_id,) if rule_id else ()
        with self.connect() as connection:
            rows = connection.execute(
                f"""SELECT d.rule_id, d.rule_version, COUNT(DISTINCT d.id) evaluations,
                    SUM(CASE WHEN f.label='confirmed_violation' THEN 1 ELSE 0 END) confirmed,
                    SUM(CASE WHEN f.label='false_positive' THEN 1 ELSE 0 END) false_positives,
                    SUM(CASE WHEN f.id IS NULL THEN 1 ELSE 0 END) unreviewed
                    FROM semantic_lint_decisions d
                    LEFT JOIN semantic_lint_feedback f ON f.decision_id=d.id
                    {where} GROUP BY d.rule_id, d.rule_version ORDER BY d.rule_id, d.rule_version""",
                params,
            ).fetchall()
            return {"rules": [dict(row) for row in rows]}

    def audit_log(
        self,
        *,
        workspace_id: str,
        harness: str = "",
        outcome: str = "",
        reason_code: str = "",
        since: str = "",
        before_id: int | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Return a bounded page of redacted event records from the local audit log."""
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if before_id is not None and before_id < 1:
            raise ValueError("before_id must be a positive event id")
        if harness and harness not in {"codex", "antigravity", "opencode"}:
            raise ValueError("harness must be codex, antigravity, or opencode")
        if outcome and outcome not in {"allow", "deny", "needs_confirmation", "abstain"}:
            raise ValueError("unsupported outcome")

        since_value = ""
        if since:
            try:
                parsed = datetime.fromisoformat(since.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("since must be an ISO-8601 timestamp with a timezone") from exc
            if parsed.tzinfo is None:
                raise ValueError("since must include a timezone")
            since_value = parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        clauses: list[str] = ["workspace_id = ?"]
        params: list[Any] = [workspace_id]
        for column, value in (
            ("harness", harness),
            ("outcome", outcome),
            ("reason_code", reason_code),
        ):
            if value:
                clauses.append(f"{column} = ?")
                params.append(value)
        if since_value:
            clauses.append("created_at >= ?")
            params.append(since_value)
        if before_id is not None:
            clauses.append("id < ?")
            params.append(before_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        sql = f"""SELECT id, event_id, harness, workspace_id, session_id, agent_id,
                         turn_id, tool_call_id, feature, feature_version, phase,
                         outcome, reason_code, source, duration_ms, timed_out,
                         error, details, created_at
                  FROM events {where}
                  ORDER BY id DESC LIMIT ?"""
        with self.connect_readonly() as connection:
            rows = connection.execute(sql, (*params, limit + 1)).fetchall()

        has_more = len(rows) > limit
        rows = rows[:limit]
        events = []
        for row in rows:
            item = dict(row)
            try:
                item["details"] = json.loads(item["details"] or "{}")
            except (TypeError, ValueError):
                item["details"] = redact(str(item["details"] or ""))
            item["error"] = redact(str(item["error"] or ""))
            events.append(item)
        return {
            "events": events,
            "has_more": has_more,
            "next_before_id": events[-1]["id"] if has_more and events else None,
        }

    def stats(self, harness: str | None = None) -> dict[str, Any]:
        self.initialize()
        where = "WHERE harness = ?" if harness else ""
        params: tuple[Any, ...] = (harness,) if harness else ()
        with self.connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*), COALESCE(AVG(duration_ms), 0.0) FROM events {where}",
                params,
            ).fetchone()
            total_events = total[0] if total else 0
            avg_duration = round(float(total[1]), 2) if total else 0.0

            harness_rows = connection.execute(
                f"SELECT harness, COUNT(*) FROM events {where} GROUP BY harness",
                params,
            ).fetchall()
            harnesses = {row[0]: row[1] for row in harness_rows}

            outcome_rows = connection.execute(
                f"SELECT outcome, COUNT(*) FROM events {where} GROUP BY outcome",
                params,
            ).fetchall()
            outcomes = {row[0]: row[1] for row in outcome_rows}

            feature_rows = connection.execute(
                f"SELECT feature, COUNT(*) FROM events {where} GROUP BY feature",
                params,
            ).fetchall()
            features = {row[0]: row[1] for row in feature_rows}

            return {
                "total_events": total_events,
                "avg_duration_ms": avg_duration,
                "harnesses": harnesses,
                "outcomes": outcomes,
                "features": features,
            }

    def record_event(self, event: Event, result: Result) -> None:
        self.initialize()
        audit_data = dict(result.data)
        if result.reason:
            audit_data["decision_reason"] = result.reason
        context_telemetry = audit_data.pop("context_telemetry", None)
        # Operational fields precede optional context so truncation cannot hide health.
        details = redact(json.dumps(audit_data, sort_keys=True, default=str), limit=1500)
        if context_telemetry is not None:
            audit_data["context_telemetry"] = context_telemetry
            details = redact(json.dumps(audit_data, default=str), limit=1500)
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
                pattern = row["pattern"]
                match = (pattern == "*") or fnmatch.fnmatch(command, pattern)
                if match:
                    return row["decision"], row["reason"], row["id"]
        return "unknown", "", None

    def save_rule(
        self,
        *,
        pattern: str,
        tool_name: str = "*",
        scope: str = "always",
        harness: str = "*",
        workspace_id: str = "",
        session_id: str = "",
        operation_digest: str = "",
        digest: str = "",
        decision: str = "allow",
        provenance: str = "manual",
        reason: str = "",
        expires_at: str | None = None,
    ) -> int:
        self.initialize()
        op_digest = digest or operation_digest
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT OR REPLACE INTO rules(
                    pattern, tool_name, scope, harness, workspace_id, session_id,
                    operation_digest, decision, provenance, reason, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    pattern, tool_name, scope, harness, workspace_id, session_id,
                    op_digest, decision, provenance, reason, expires_at,
                ),
            )
            return int(cursor.lastrowid or 0)

    def consume_rule(self, rule_id: int) -> bool:
        self.initialize()
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE rules SET consumed_at = CURRENT_TIMESTAMP WHERE id = ? AND consumed_at IS NULL",
                (rule_id,),
            )
            return cursor.rowcount > 0

    def claim(
        self,
        event: Event,
        feature: str,
        phase: str,
        digest: str,
        policy_version: str,
        lease_seconds: float = 5.0,
    ) -> Claim:
        self.initialize()
        claim_key = f"{event.harness.value}:{event.session_id}:{event.turn_id}:{event.tool_call_id}:{feature}:{phase}:{digest}"
        now = time.time()
        lease_expires = now + lease_seconds
        with self.connect() as connection:
            row = connection.execute(
                "SELECT status, lease_expires_at, result_json FROM invocations WHERE claim_key = ?",
                (claim_key,),
            ).fetchone()
            if row is not None:
                if row["status"] == "complete" and row["result_json"]:
                    data = json.loads(row["result_json"])
                    return Claim(status="replay", result=Result(
                        outcome=Outcome(data["outcome"]),
                        reason=data.get("reason", ""),
                        reason_code=data.get("reason_code", ""),
                        feature=data.get("feature", feature),
                        feature_version=data.get("feature_version", policy_version),
                        source=data.get("source", "replay"),
                        cached=True,
                    ))
                if row["status"] == "active" and row["lease_expires_at"] > now:
                    return Claim(status="active")
            connection.execute(
                """INSERT INTO invocations (
                    claim_key, harness, workspace_id, session_id, invocation_id,
                    feature, phase, operation_digest, policy_version, status, lease_expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
                ON CONFLICT(claim_key) DO UPDATE SET
                    status = 'active',
                    lease_expires_at = excluded.lease_expires_at,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    claim_key, event.harness.value, event.workspace_id, event.session_id,
                    event.tool_call_id, feature, phase, digest, policy_version, lease_expires,
                ),
            )
            return Claim(status="acquired")

    def complete_claim(
        self,
        event: Event,
        feature: str,
        phase: str,
        result: Result,
        rule_id: int | None = None,
        digest: str = "",
    ) -> Result:
        self.initialize()
        claim_digest = digest or result.data.get("digest", "")
        claim_key = f"{event.harness.value}:{event.session_id}:{event.turn_id}:{event.tool_call_id}:{feature}:{phase}:{claim_digest}"
        payload = json.dumps({
            "outcome": result.outcome.value,
            "reason": result.reason,
            "reason_code": result.reason_code,
            "feature": result.feature,
            "feature_version": result.feature_version,
            "source": result.source,
        })
        with self.connect() as connection:
            if rule_id is not None:
                consumed = connection.execute(
                    "UPDATE rules SET consumed_at = CURRENT_TIMESTAMP WHERE id = ? AND consumed_at IS NULL",
                    (rule_id,),
                ).rowcount > 0
                if not consumed:
                    return Result(
                        outcome=Outcome.DENY,
                        reason="One-use rule was already consumed.",
                        reason_code="authorization_already_consumed",
                        feature=feature,
                        feature_version=result.feature_version,
                    )
            connection.execute(
                """UPDATE invocations
                   SET status = 'complete', result_json = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE claim_key = ?""",
                (payload, claim_key),
            )
        return result
