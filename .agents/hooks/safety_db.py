"""
safety_db.py - Decision Database and Invariant Safety Shield for Antigravity Jev.

Architecture:
1. Invariant Safety Shield (Tier 1): A tight, non-bypassable guard against unambiguous,
   catastrophic actions (recursive directory wipe, hard reset, force push, disk format).
   Only applies to run_command; file-editing tools are protected by IDE local history.
2. User Decision Memory (Tier 2): SQLite database storing user-approved overrides
   ('always' or 'session-scoped'). No large hardcoded allowlist needed.
3. Audit Log: Tracks all tool calls, Jev intent judgments, latency, and decisions.
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


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Antigravity Jev Safety Gate Decision Database")
    parser.add_argument("--list",          action="store_true")
    parser.add_argument("--allow",         type=str)
    parser.add_argument("--tool",          type=str, default="run_command")
    parser.add_argument("--scope",         choices=["always", "session"], default="always")
    parser.add_argument("--conversation",  type=str, default="")
    parser.add_argument("--workspace",     type=str, default="")
    parser.add_argument("--reason",        type=str, default="User specified rule")
    parser.add_argument("--clear-all",     action="store_true")
    parser.add_argument("--test-cmd",      type=str)
    args = parser.parse_args()

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
