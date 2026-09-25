"""
safety_db.py - Decision Database, Invariant Safety Shield, and Audit Lifecycle for Antigravity Jev.

Architecture:
1. Invariant Safety Shield (Tier 1): A tight, non-bypassable guard against unambiguous,
   catastrophic actions (recursive directory wipe, hard reset, force push, disk format).
   Only applies to run_command; file-editing tools are protected by IDE local history.
2. User Decision Memory (Tier 2): SQLite database storing user-approved overrides
   ('always' or 'session-scoped'). No large hardcoded allowlist needed.
   Session rules auto-expire after 30 days.
3. Audit Log: Tracks all tool calls, Jev intent judgments, latency, and decisions.
   Retains all records until manually pruned with `--prune`.
4. Security Review: Built-in `--review` tool for inspecting intercepted commands,
   false positive analysis, and prompt/rule optimization.
5. Speculative Fan-Out Active Learning: `--review-speculative` tool for auditing
   speculative evaluations, ambiguity accuracy, and user calibration replies.
"""

import os
import re
import sys
import fnmatch
import sqlite3
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

DEFAULT_DB_PATH = Path(os.path.expanduser("~/.gemini/config/safety_decisions.db"))

# Tools where the critical shell shield does NOT apply.
# Their args are serialized file paths/content (never executed in the OS shell).
SKIP_CRITICAL_TOOLS = {"write_to_file", "replace_file_content", "multi_replace_file_content"}

# Python runner pattern - only examines interpreter + script path, NOT CLI arguments
# (prevents false positives when test runners pass dangerous commands as test arguments).
_PYTHON_RUNNER_RE = re.compile(r"(?i)^(python3?\.?\d*|py\.?\d*)\s+")

# Invariant Safety Shield: Operations that ALWAYS require explicit confirmation.
# Cannot be bypassed via database rules. Kept minimal and non-negotiable.
CRITICAL_PATTERNS = [
    # Recursive / force deletion
    (r"(?i)\brmdir\b.*\B/s\b",                                    "Recursive directory removal (rmdir /s)"),
    (r"(?i)\brd\b.*\B/s\b",                                       "Recursive directory removal (rd /s)"),
    (r"(?i)\bdel\b.*\B/s\b",                                      "Recursive file deletion (del /s)"),
    (r"(?i)\berase\b.*\B/s\b",                                    "Recursive deletion (erase /s)"),
    (r"(?i)\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r|--recursive)\b", "Recursive force removal (rm -rf)"),
    # Destructive git operations
    (r"(?i)\bgit\s+reset\s+--hard\b",                             "Hard git reset discarding uncommitted work"),
    (r"(?i)\bgit\s+clean\s+-[a-zA-Z]*f\b",                       "Untracked files force cleanup (git clean -f)"),
    (r"(?i)\bgit\s+push\s+.*--force\b",                           "Force push overwriting remote history"),
    (r"(?i)\bgit\s+push\s+-f\b",                                  "Force push (-f) overwriting remote history"),
    (r"(?i)\bgit\s+checkout\s+--\s+\.",                           "Git checkout discarding all local file changes"),
    (r"(?i)\bgit\s+restore\s+\.",                                  "Git restore discarding working tree changes"),
    (r"(?i)\bgit\s+branch\s+-D\b",                                "Force branch deletion"),
    # Disk / System format
    (r"(?i)\bformat\s+[a-zA-Z]:",                                 "Disk format operation"),
    (r"(?i)\bdiskpart\b",                                          "Disk partition utility"),
    (r"(?i)\bfdisk\b",                                             "Disk partition utility"),
    (r"(?i)\bmkfs\b",                                              "Filesystem creation"),
    # Remote shell / payload piping
    (r"(?i)\b(curl|wget)\b.*\|\s*(bash|sh|powershell|pwsh|cmd)\b", "Piping downloaded remote payload directly into shell"),
    # Database destruction
    (r"(?i)\bDROP\s+(DATABASE|SCHEMA)\b",                         "Database schema drop"),
    (r"(?i)\bTRUNCATE\s+TABLE\b",                                 "Table truncate operation"),
]


def get_db_path() -> Path:
    db_path = DEFAULT_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or get_db_path()
    conn = sqlite3.connect(str(path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[Path] = None):
    """Initializes tables for user-saved rules and audit logs. Zero hardcoded rules seeded."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern TEXT NOT NULL,
                    tool_name TEXT NOT NULL DEFAULT '*',
                    scope TEXT NOT NULL CHECK(scope IN ('always', 'session')),
                    conversation_id TEXT NOT NULL DEFAULT '',
                    workspace_path TEXT NOT NULL DEFAULT '',
                    decision TEXT NOT NULL CHECK(decision IN ('allow', 'deny')),
                    reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(pattern, tool_name, scope, conversation_id, workspace_path)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS decision_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    conversation_id TEXT,
                    tool_name TEXT,
                    command TEXT,
                    routine_score REAL,
                    risk_score REAL,
                    decision TEXT,
                    source TEXT,
                    reason TEXT
                )
            """)
            # Schema migration: ensure routine_score and risk_score columns exist
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(decision_log)").fetchall()}
            if "routine_score" not in cols:
                conn.execute("ALTER TABLE decision_log ADD COLUMN routine_score REAL DEFAULT 0.0")
            if "risk_score" not in cols:
                conn.execute("ALTER TABLE decision_log ADD COLUMN risk_score REAL DEFAULT 0.0")

            # Auto-expire session rules older than 30 days
            conn.execute("""
                DELETE FROM rules
                WHERE scope = 'session'
                  AND created_at < datetime('now', '-30 days')
            """)

            # Table for Speculative Fan-Out & Ambiguity Arbitrations (Proposal 21 Active Learning)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS speculative_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    conversation_id TEXT,
                    prompt TEXT,
                    latency_ms REAL,
                    needs_git_diff REAL,
                    needs_test_log REAL,
                    ambiguity_score REAL,
                    ambiguity_conf REAL,
                    suggested_action TEXT,
                    suggested_conf REAL,
                    actions_taken TEXT,
                    user_reply TEXT DEFAULT '',
                    feedback_label TEXT DEFAULT 'pending'
                )
            """)
    finally:
        conn.close()


def _extract_check_string(tool_name: str, command: str) -> str:
    """
    Returns the portion of the command string to check against CRITICAL_PATTERNS.
    Strips 'cmd /c', compound operators, and extracts python runner without CLI arguments.
    """
    s = command.strip()
    if s.lower().startswith("cmd /c "):
        s = s[7:].strip()
    elif s.lower().startswith("cmd.exe /c "):
        s = s[11:].strip()
    if s.startswith('"') and s.endswith('"'):
        s = s[1:-1].strip()

    first_part = re.split(r"\s+&&\s+|\s+\|\|\s+|\s+\|\s+", s)[0].strip()

    if _PYTHON_RUNNER_RE.match(first_part):
        tokens = first_part.split(None, 2)
        return " ".join(tokens[:2]) if len(tokens) >= 2 else first_part

    return first_part


def is_critical(tool_name: str, command: str) -> Tuple[bool, str]:
    """
    Returns (True, reason) if the operation matches the invariant critical shield.
    File-editing tools always return False (handled by IDE workspace protections).
    """
    if tool_name in SKIP_CRITICAL_TOOLS:
        return False, ""

    check_str = _extract_check_string(tool_name, command)
    for pattern, description in CRITICAL_PATTERNS:
        if re.search(pattern, check_str):
            return True, description
    return False, ""


def clean_command_string(command: str) -> str:
    """Strips cmd /c wrappers and surrounding quotes for pattern matching / display."""
    s = command.strip()
    if s.lower().startswith("cmd /c "):
        s = s[7:].strip()
    elif s.lower().startswith("cmd.exe /c "):
        s = s[11:].strip()
    return s.strip("\"'")


def check_decision(
    tool_name: str,
    command: str,
    conversation_id: str = "",
    workspace_path: str = "",
) -> Tuple[str, str]:
    """
    Checks the user decision DB.
    Returns (decision, reason) where decision is 'allow', 'deny', 'force_ask', or 'unknown'.
    """
    critical, crit_reason = is_critical(tool_name, command)
    if critical:
        return "force_ask", f"Critical destructive operation: {crit_reason}"

    init_db()
    conn = get_connection()
    try:
        clean_cmd = clean_command_string(command)
        cur = conn.execute("""
            SELECT pattern, tool_name, scope, decision, reason, conversation_id, workspace_path
            FROM rules
            WHERE (tool_name = ? OR tool_name = '*')
              AND (
                  scope = 'always'
                  OR (scope = 'session' AND (conversation_id = ? OR conversation_id = ''))
              )
            ORDER BY scope DESC, id DESC
        """, (tool_name, conversation_id))

        for row in cur.fetchall():
            pattern = row["pattern"]
            if row["workspace_path"] and workspace_path:
                if not workspace_path.lower().startswith(row["workspace_path"].lower()):
                    continue
            if (
                pattern == "*"
                or fnmatch.fnmatch(clean_cmd.lower(), pattern.lower())
                or clean_cmd.lower().startswith(pattern.lower().rstrip("*").strip())
            ):
                return row["decision"], f"Matched user {row['scope']} rule '{pattern}': {row['reason'] or ''}"

        return "unknown", ""
    finally:
        conn.close()


def save_decision(
    pattern: str,
    tool_name: str = "*",
    scope: str = "always",
    decision: str = "allow",
    conversation_id: Optional[str] = None,
    workspace_path: Optional[str] = None,
    reason: str = "",
) -> bool:
    """Saves an approval/denial rule. Rejects saving 'allow' for critical invariants."""
    critical, crit_reason = is_critical(tool_name, pattern)
    if critical and decision == "allow":
        raise ValueError(f"Cannot save 'allow' rule for critical operation: {crit_reason}")

    init_db()
    conn = get_connection()
    try:
        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO rules
                    (pattern, tool_name, scope, conversation_id, workspace_path, decision, reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (pattern, tool_name, scope,
                  conversation_id or "", workspace_path or "",
                  decision, reason))
        return True
    finally:
        conn.close()


def log_decision(
    conversation_id: str,
    tool_name: str,
    command: str,
    routine_score: float,
    risk_score: float,
    decision: str,
    source: str,
    reason: str,
):
    """Logs the final safety gate decision for auditability."""
    try:
        init_db()
        conn = get_connection()
        try:
            with conn:
                conn.execute("""
                    INSERT INTO decision_log
                        (conversation_id, tool_name, command, routine_score, risk_score,
                         decision, source, reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (conversation_id, tool_name, command[:500],
                      routine_score, risk_score, decision, source, reason))
        finally:
            conn.close()
    except Exception:
        pass


def list_rules(scope: Optional[str] = None) -> List[Dict[str, Any]]:
    init_db()
    conn = get_connection()
    try:
        if scope:
            cur = conn.execute("SELECT * FROM rules WHERE scope = ? ORDER BY id ASC", (scope,))
        else:
            cur = conn.execute("SELECT * FROM rules ORDER BY scope DESC, id ASC")
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def clear_session_rules(conversation_id: str) -> int:
    init_db()
    conn = get_connection()
    try:
        with conn:
            cur = conn.execute(
                "DELETE FROM rules WHERE scope = 'session' AND conversation_id = ?",
                (conversation_id,)
            )
            return cur.rowcount
    finally:
        conn.close()


def clear_all_rules() -> int:
    init_db()
    conn = get_connection()
    try:
        with conn:
            cur = conn.execute("DELETE FROM rules")
            return cur.rowcount
    finally:
        conn.close()


def prune_db(days: int = 30) -> Tuple[int, int]:
    """
    Manually prunes decision_log records and session rules older than `days` days.
    Returns (pruned_logs_count, pruned_session_rules_count).
    """
    init_db()
    conn = get_connection()
    try:
        with conn:
            cur1 = conn.execute(
                "DELETE FROM decision_log WHERE timestamp < datetime('now', ?)",
                (f"-{days} days",)
            )
            pruned_logs = cur1.rowcount
            cur2 = conn.execute(
                "DELETE FROM rules WHERE scope = 'session' AND created_at < datetime('now', ?)",
                (f"-{days} days",)
            )
            pruned_rules = cur2.rowcount
            return pruned_logs, pruned_rules
    finally:
        conn.close()


def get_review_stats() -> Dict[str, Any]:
    """Queries the audit log and returns aggregated statistics for security review."""
    init_db()
    conn = get_connection()
    try:
        total_decisions = conn.execute("SELECT COUNT(*) FROM decision_log").fetchone()[0]

        decisions_by_type = {}
        for r in conn.execute("SELECT decision, COUNT(*) as cnt FROM decision_log GROUP BY decision").fetchall():
            decisions_by_type[r["decision"]] = r["cnt"]

        sources_breakdown = {}
        for r in conn.execute("SELECT source, COUNT(*) as cnt FROM decision_log GROUP BY source").fetchall():
            sources_breakdown[r["source"]] = r["cnt"]

        intercepted = []
        for r in conn.execute("""
            SELECT command, tool_name, source, routine_score, risk_score, reason, COUNT(*) as count
            FROM decision_log
            WHERE decision = 'force_ask'
            GROUP BY command, tool_name, source
            ORDER BY count DESC, risk_score DESC
            LIMIT 15
        """).fetchall():
            intercepted.append(dict(r))

        recent_decisions = []
        for r in conn.execute("""
            SELECT timestamp, tool_name, command, source, decision, routine_score, risk_score
            FROM decision_log
            ORDER BY id DESC
            LIMIT 10
        """).fetchall():
            recent_decisions.append(dict(r))

        rules_always = conn.execute("SELECT COUNT(*) FROM rules WHERE scope = 'always'").fetchone()[0]
        rules_session = conn.execute("SELECT COUNT(*) FROM rules WHERE scope = 'session'").fetchone()[0]

        return {
            "total_decisions": total_decisions,
            "decisions_by_type": decisions_by_type,
            "sources": sources_breakdown,
            "intercepted": intercepted,
            "recent_decisions": recent_decisions,
            "rules_always": rules_always,
            "rules_session": rules_session,
        }
    finally:
        conn.close()


def log_speculative_decision(
    conversation_id: str,
    prompt: str,
    latency_ms: float,
    needs_git: float,
    needs_test: float,
    ambiguity_score: float,
    ambiguity_conf: float,
    suggested_action: str,
    suggested_conf: float,
    actions_taken: List[str],
    db_path: Optional[Path] = None
) -> int:
    """Logs a speculative pre-flight evaluation to SQLite for active tuning and audit."""
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        with conn:
            cur = conn.execute("""
                INSERT INTO speculative_decisions (
                    conversation_id, prompt, latency_ms,
                    needs_git_diff, needs_test_log,
                    ambiguity_score, ambiguity_conf,
                    suggested_action, suggested_conf,
                    actions_taken, feedback_label
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                conversation_id or "", prompt, latency_ms,
                needs_git, needs_test,
                ambiguity_score, ambiguity_conf,
                suggested_action, suggested_conf,
                ", ".join(actions_taken) if actions_taken else "none",
                "pending"
            ))
            return cur.lastrowid
    except Exception:
        return -1
    finally:
        conn.close()


def record_speculative_feedback(
    conversation_id: str,
    user_reply: str,
    feedback_label: str = "clarified",
    db_path: Optional[Path] = None
):
    """Updates the pending speculative decision record with developer feedback."""
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute("""
                UPDATE speculative_decisions
                SET user_reply = ?, feedback_label = ?
                WHERE id = (
                    SELECT id FROM speculative_decisions
                    WHERE (conversation_id = ? OR conversation_id = '') AND feedback_label = 'pending'
                    ORDER BY id DESC LIMIT 1
                )
            """, (user_reply, feedback_label, conversation_id or ""))
    except Exception:
        pass
    finally:
        conn.close()


def print_speculative_review(db_path: Optional[Path] = None):
    """Prints diagnostic review of speculative router evaluations and ambiguity calibration."""
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        total = conn.execute("SELECT COUNT(*) FROM speculative_decisions").fetchone()[0]
        ambig_count = conn.execute("SELECT COUNT(*) FROM speculative_decisions WHERE ambiguity_score >= 1.75").fetchone()[0]
        git_count = conn.execute("SELECT COUNT(*) FROM speculative_decisions WHERE needs_git_diff >= 0.65").fetchone()[0]
        test_count = conn.execute("SELECT COUNT(*) FROM speculative_decisions WHERE needs_test_log >= 0.65").fetchone()[0]
        clarified = conn.execute("SELECT COUNT(*) FROM speculative_decisions WHERE feedback_label = 'clarified'").fetchone()[0]

        recent = conn.execute("""
            SELECT timestamp, prompt, latency_ms, ambiguity_score, actions_taken, user_reply, feedback_label
            FROM speculative_decisions
            ORDER BY id DESC LIMIT 10
        """).fetchall()

        print(f"\n{'='*75}")
        print(f" JEV SPECULATIVE ARBITER & ACTIVE LEARNING AUDIT")
        print(f" Database: {db_path or get_db_path()}")
        print(f"{'='*75}\n")

        print(f"Summary:")
        print(f"  Total Evaluated Turns : {total}")
        print(f"  Ambiguity Alerts      : {ambig_count}")
        print(f"  Git Prefetches        : {git_count}")
        print(f"  Test Prefetches       : {test_count}")
        print(f"  Clarifications Logged : {clarified}")

        if recent:
            print(f"\nRecent Speculative Turns:")
            print(f"  {'Timestamp':<19} {'Lat':<6} {'Ambig':<6} {'Action':<22} Prompt")
            print(f"  {'-'*75}")
            for r in recent:
                p_short = r['prompt'].replace('\n', ' ')[:32]
                print(f"  {r['timestamp'][:19]:<19} {r['latency_ms']:<6.0f} {r['ambiguity_score']:<6.1f} {r['actions_taken']:<22} {p_short}")
                if r['user_reply']:
                    print(f"    -> User Reply: {r['user_reply'][:60]} ({r['feedback_label']})")
        print(f"\n{'='*75}\n")
    finally:
        conn.close()


def print_review():
    """Prints a formatted security review of the audit log."""
    stats = get_review_stats()
    db_path = get_db_path()

    print(f"\n{'='*75}")
    print(f" JEV SAFETY GATE SECURITY AUDIT REVIEW")
    print(f" Database: {db_path}")
    print(f"{'='*75}\n")

    print(f"Summary:")
    print(f"  Total Logged Events    : {stats['total_decisions']}")
    print(f"  Allowed                : {stats['decisions_by_type'].get('allow', 0)}")
    print(f"  Intercepted (force_ask): {stats['decisions_by_type'].get('force_ask', 0)}")

    print(f"\nRouting Sources:")
    for src, count in stats['sources'].items():
        print(f"  {src:<22}: {count}")

    print(f"\nActive Rules in Memory:")
    print(f"  Permanent ('always')   : {stats['rules_always']}")
    print(f"  Session-scoped         : {stats['rules_session']} (auto-expires after 30 days)")

    if stats["intercepted"]:
        print(f"\nTop Intercepted Actions:")
        print(f"  {'Count':<6} {'Source':<16} {'Tool':<14} Command")
        print(f"  {'-'*70}")
        for item in stats["intercepted"]:
            cmd_short = item['command'].replace('\n', ' ')[:45]
            print(f"  {item['count']:<6} {item['source']:<16} {item['tool_name']:<14} {cmd_short}")
    else:
        print(f"\nTop Intercepted Actions: None recorded.")

    if stats["recent_decisions"]:
        print(f"\nRecent Activity Log (Latest 10):")
        print(f"  {'Time':<20} {'Decision':<10} {'Source':<16} Command")
        print(f"  {'-'*70}")
        for r in stats["recent_decisions"]:
            cmd_short = r['command'].replace('\n', ' ')[:38]
            print(f"  {r['timestamp'][:19]:<20} {r['decision']:<10} {r['source']:<16} {cmd_short}")

    print(f"\n{'='*75}\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Antigravity Jev Safety Gate Decision Database")
    parser.add_argument("--list",          action="store_true", help="List active saved rules")
    parser.add_argument("--review",        action="store_true", help="Review audit log and security statistics")
    parser.add_argument("--review-speculative", action="store_true", help="Review speculative fan-out and ambiguity audit")
    parser.add_argument("--prune",         action="store_true", help="Prune logs and session rules older than --days")
    parser.add_argument("--days",          type=int, default=30, help="Days threshold for pruning (default: 30)")
    parser.add_argument("--allow",         type=str, help="Add permanent or session allow rule pattern")
    parser.add_argument("--tool",          type=str, default="run_command")
    parser.add_argument("--scope",         choices=["always", "session"], default="always")
    parser.add_argument("--conversation",  type=str, default="")
    parser.add_argument("--workspace",     type=str, default="")
    parser.add_argument("--reason",        type=str, default="User specified rule")
    parser.add_argument("--clear-all",     action="store_true", help="Clear all saved rules")
    parser.add_argument("--test-cmd",      type=str, help="Test how a command resolves")
    args = parser.parse_args()

    if args.review_speculative:
        print_speculative_review()
        sys.exit(0)

    if args.review:
        print_review()
        sys.exit(0)

    if args.prune:
        p_logs, p_rules = prune_db(args.days)
        print(f"[+] Pruned {p_logs} log entries and {p_rules} session rules older than {args.days} days.")
        sys.exit(0)

    if args.clear_all:
        count = clear_all_rules()
        print(f"[+] Cleared {count} rules from decision database.")
        sys.exit(0)

    if args.allow:
        try:
            save_decision(args.allow, tool_name=args.tool, scope=args.scope,
                          conversation_id=args.conversation or None,
                          workspace_path=args.workspace or None,
                          reason=args.reason)
            print(f"[+] Saved '{args.allow}' ({args.scope}) for tool '{args.tool}'.")
        except ValueError as e:
            print(f"[-] Failed: {e}")
        sys.exit(0)

    if args.test_cmd:
        crit, crit_r = is_critical(args.tool, args.test_cmd)
        chk = _extract_check_string(args.tool, args.test_cmd)
        dec, dec_r = check_decision(args.tool, args.test_cmd, args.conversation, args.workspace)
        print(f"Command      : {args.test_cmd}")
        print(f"Effective str: {chk}")
        print(f"Critical     : {crit} -- {crit_r or 'n/a'}")
        print(f"DB Decision  : {dec} -- {dec_r or 'n/a'}")
        sys.exit(0)

    rules = list_rules()
    print(f"=== Jev Safety Gate Decision Database ({get_db_path()}) ===")
    print(f"Total: {len(rules)} rules\n")
    print(f"{'ID':<4} {'Scope':<10} {'Tool':<24} {'Dec':<7} {'Pattern':<30} Reason")
    print("-" * 95)
    for r in rules:
        cid = f"[{r['conversation_id'][:8]}]" if r["conversation_id"] else ""
        scope_col = f"{r['scope']} {cid}".strip()
        print(f"{r['id']:<4} {scope_col:<10} {r['tool_name']:<24} {r['decision']:<7} {r['pattern']:<30} {r['reason'] or ''}")
