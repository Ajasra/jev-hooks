"""
safety_db.py - Decision Database and Critical Operation Shield for Antigravity Jev Safety Gate.

Provides:
1. Deterministic Critical Shield: High-impact / destructive operations ALWAYS require confirmation (force_ask).
2. Decision Database: SQLite persistence for session-level and permanent ('always') approval rules.
3. Audit Log: Tracks all safety gate decisions, latency, and scores.
"""

import os
import re
import sys
import fnmatch
import sqlite3
import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

# Default DB location in user's global config directory
DEFAULT_DB_PATH = Path(os.path.expanduser("~/.gemini/config/safety_decisions.db"))

# Critical regex patterns that can NEVER be auto-approved
CRITICAL_PATTERNS = [
    # Recursive / force deletion
    (r"(?i)\brmdir\s+.*(/s|\\s)", "Recursive directory removal (rmdir /s)"),
    (r"(?i)\brd\s+.*(/s|\\s)", "Recursive directory removal (rd /s)"),
    (r"(?i)\bdel\s+.*(/s|\\s)", "Recursive file deletion (del /s)"),
    (r"(?i)\berase\s+.*(/s|\\s)", "Recursive deletion (erase /s)"),
    (r"(?i)\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r|--recursive)", "Recursive force removal (rm -rf)"),
    # Destructive git operations
    (r"(?i)\bgit\s+reset\s+--hard\b", "Hard git reset discarding uncommitted work"),
    (r"(?i)\bgit\s+clean\s+(-[a-zA-Z]*f|--force)", "Untracked files force cleanup (git clean -f)"),
    (r"(?i)\bgit\s+push\s+.*(--force|-f\b)", "Force push overwriting remote history"),
    (r"(?i)\bgit\s+checkout\s+(--\s+\.|\.\b)", "Git checkout discarding all local file changes"),
    (r"(?i)\bgit\s+restore\s+(\.|\*)\b", "Git restore discarding working tree changes"),
    (r"(?i)\bgit\s+branch\s+(-D|--delete\s+--force)\b", "Force branch deletion"),
    # Disk / System format
    (r"(?i)\bformat\s+[a-zA-Z]:", "Disk format operation"),
    (r"(?i)\bdiskpart\b", "Disk partition utility"),
    (r"(?i)\bfdisk\b", "Disk partition utility"),
    (r"(?i)\bmkfs\b", "Filesystem creation"),
    # Database destruction
    (r"(?i)\b(DROP\s+DATABASE|DROP\s+SCHEMA)\b", "Database schema drop"),
    (r"(?i)\bTRUNCATE\s+TABLE\b", "Table truncate operation"),
]

# Default safe patterns pre-seeded in the database
DEFAULT_SAFE_RULES = [
    # Standard git workflow commands (never destructive)
    ("git status*", "run_command", "always", "Standard status check"),
    ("git diff*", "run_command", "always", "Standard diff inspection"),
    ("git log*", "run_command", "always", "Standard commit log"),
    ("git show*", "run_command", "always", "Standard commit inspection"),
    ("git add*", "run_command", "always", "Staging files for commit"),
    ("git commit*", "run_command", "always", "Committing staged changes"),
    ("git push", "run_command", "always", "Standard git push"),
    ("git push origin *", "run_command", "always", "Pushing to remote origin (non-force)"),
    ("git push -u origin *", "run_command", "always", "Setting upstream and pushing (non-force)"),
    ("git pull*", "run_command", "always", "Pulling updates from remote"),
    ("git fetch*", "run_command", "always", "Fetching remote references"),
    ("git checkout *", "run_command", "always", "Branch switching or creation"),
    ("git switch *", "run_command", "always", "Branch switching"),
    ("git branch*", "run_command", "always", "Branch listing or creation"),
    ("git stash*", "run_command", "always", "Working state stashing"),
    ("git merge*", "run_command", "always", "Branch merging"),
    # Routine developer build / test / run
    ("npm test*", "run_command", "always", "Running test suite"),
    ("npm run *", "run_command", "always", "Running npm script"),
    ("pytest*", "run_command", "always", "Running pytest"),
    ("uv run *", "run_command", "always", "Running via uv"),
    ("python -m unittest*", "run_command", "always", "Running unit tests"),
    # File mutation operations - always allowed
    ("*", "write_to_file", "always", "Standard file write"),
    ("*", "replace_file_content", "always", "Standard file edit/replace"),
    ("*", "multi_replace_file_content", "always", "Standard multi-edit/replace"),
]


def get_db_path() -> Path:
    """Returns the database file path, ensuring parent directory exists."""
    db_path = DEFAULT_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or get_db_path()
    conn = sqlite3.connect(str(path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[Path] = None):
    """Initializes tables and seeds default rules if empty."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern TEXT NOT NULL,
                    tool_name TEXT NOT NULL DEFAULT '*',
                    scope TEXT NOT NULL CHECK(scope IN ('always', 'session')),
                    conversation_id TEXT,
                    workspace_path TEXT,
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
                    blast_score REAL,
                    is_destructive REAL,
                    decision TEXT,
                    source TEXT,
                    reason TEXT
                )
            """)

            # Seed default safe rules if rules table is completely empty
            cur = conn.execute("SELECT COUNT(*) FROM rules")
            count = cur.fetchone()[0]
            if count == 0:
                for pattern, tool, scope, reason in DEFAULT_SAFE_RULES:
                    conn.execute("""
                        INSERT OR IGNORE INTO rules (pattern, tool_name, scope, decision, reason)
                        VALUES (?, ?, ?, 'allow', ?)
                    """, (pattern, tool, scope, reason))
    finally:
        conn.close()


def is_critical(tool_name: str, command: str) -> Tuple[bool, str]:
    """
    Evaluates whether an action is inherently critical or destructive.
    Critical actions CANNOT be bypassed by session or permanent rules.
    """
    clean_cmd = command.strip()
    if clean_cmd.lower().startswith("cmd /c "):
        clean_cmd = clean_cmd[7:].strip()
    elif clean_cmd.lower().startswith("cmd.exe /c "):
        clean_cmd = clean_cmd[11:].strip()

    for pattern, description in CRITICAL_PATTERNS:
        if re.search(pattern, clean_cmd):
            return True, description

    return False, ""


def clean_command_string(command: str) -> str:
    """Strips outer cmd /c wrappers and quotes for pattern matching."""
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
    workspace_path: str = ""
) -> Tuple[str, str]:
    """
    Checks the decision database for an existing rule.
    Returns (decision, reason) where decision is 'allow', 'deny', or 'unknown'.
    """
    # Critical operations always escalate regardless of DB
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
                  OR (scope = 'session' AND (conversation_id = ? OR conversation_id IS NULL OR conversation_id = ''))
              )
            ORDER BY scope DESC, id DESC
        """, (tool_name, conversation_id))

        rows = cur.fetchall()
        for row in rows:
            pattern = row["pattern"]

            if row["workspace_path"] and workspace_path:
                if not workspace_path.lower().startswith(row["workspace_path"].lower()):
                    continue

            if (
                pattern == "*"
                or fnmatch.fnmatch(clean_cmd.lower(), pattern.lower())
                or clean_cmd.lower().startswith(pattern.lower().rstrip("*"))
            ):
                return row["decision"], f"Matched {row['scope']} rule '{pattern}': {row['reason'] or ''}"

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
    reason: str = ""
) -> bool:
    """Saves an approval/denial rule. Rejects saving 'allow' for critical operations."""
    critical, crit_reason = is_critical(tool_name, pattern)
    if critical and decision == "allow":
        raise ValueError(f"Cannot save 'allow' rule for critical operation: {crit_reason}")

    init_db()
    conn = get_connection()
    try:
        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO rules
                (pattern, tool_name, scope, decision, conversation_id, workspace_path, reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (pattern, tool_name, scope, decision, conversation_id, workspace_path, reason))
        return True
    finally:
        conn.close()


def log_decision(
    conversation_id: str,
    tool_name: str,
    command: str,
    blast_score: float,
    is_destructive: float,
    decision: str,
    source: str,
    reason: str
):
    """Logs the final safety gate decision for auditability."""
    try:
        init_db()
        conn = get_connection()
        try:
            with conn:
                conn.execute("""
                    INSERT INTO decision_log
                    (conversation_id, tool_name, command, blast_score, is_destructive, decision, source, reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (conversation_id, tool_name, command[:500], blast_score, is_destructive, decision, source, reason))
        finally:
            conn.close()
    except Exception:
        pass


def list_rules(scope: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns a list of all active rules."""
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
    """Cleans up session-level rules for a closed conversation."""
    init_db()
    conn = get_connection()
    try:
        with conn:
            cur = conn.execute("DELETE FROM rules WHERE scope = 'session' AND conversation_id = ?", (conversation_id,))
            return cur.rowcount
    finally:
        conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Antigravity Jev Safety Gate Decision Database")
    parser.add_argument("--list", action="store_true", help="List all configured rules")
    parser.add_argument("--allow", type=str, help="Pattern to allow (e.g. 'git commit*')")
    parser.add_argument("--tool", type=str, default="run_command")
    parser.add_argument("--scope", choices=["always", "session"], default="always")
    parser.add_argument("--conversation", type=str, default="")
    parser.add_argument("--reason", type=str, default="User specified rule")
    parser.add_argument("--init-defaults", action="store_true")
    parser.add_argument("--test-cmd", type=str)

    args = parser.parse_args()

    if args.init_defaults:
        init_db()
        print("[+] Decision database initialized with default rules.")
        sys.exit(0)

    if args.allow:
        try:
            save_decision(args.allow, tool_name=args.tool, scope=args.scope,
                          conversation_id=args.conversation or None, reason=args.reason)
            print(f"[+] Saved '{args.allow}' ({args.scope}) to decision database.")
        except ValueError as e:
            print(f"[-] Failed: {e}")
        sys.exit(0)

    if args.test_cmd:
        crit, crit_r = is_critical(args.tool, args.test_cmd)
        dec, dec_r = check_decision(args.tool, args.test_cmd, args.conversation)
        print(f"Command    : {args.test_cmd}")
        print(f"Critical   : {crit} — {crit_r}")
        print(f"DB Decision: {dec} — {dec_r}")
        sys.exit(0)

    rules = list_rules()
    print(f"=== Jev Safety Gate Decision Database ({get_db_path()}) ===")
    print(f"Total: {len(rules)} rules\n")
    print(f"{'ID':<4} {'Scope':<10} {'Tool':<22} {'Dec':<7} {'Pattern':<30} Reason")
    print("-" * 90)
    for r in rules:
        cid = f"[{r['conversation_id'][:8]}]" if r["conversation_id"] else ""
        scope_col = f"{r['scope']} {cid}".strip()
        print(f"{r['id']:<4} {scope_col:<10} {r['tool_name']:<22} {r['decision']:<7} {r['pattern']:<30} {r['reason'] or ''}")
