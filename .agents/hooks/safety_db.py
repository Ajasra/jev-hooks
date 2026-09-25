"""
safety_db.py - Decision Database and Critical Operation Shield for Antigravity Jev Safety Gate.

Provides:
1. Deterministic Critical Shield: High-impact / destructive shell operations ALWAYS require
   confirmation. Only applies to run_command — file write tools are never destructive at the
   shell level and their args may contain dangerous strings in documentation/code content.
2. Decision Database: SQLite persistence for session-level and permanent ('always') approval rules.
3. Audit Log: Tracks all safety gate decisions, latency, and scores.
"""

import os
import re
import sys
import fnmatch
import sqlite3
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

DEFAULT_DB_PATH = Path(os.path.expanduser("~/.gemini/config/safety_decisions.db"))

# Tools where the critical shell-command shield does NOT apply.
# Their 'command' string is serialized tool args (may contain dangerous strings in
# CodeContent / documentation). The OS shell is never invoked for these tools.
SKIP_CRITICAL_TOOLS = {"write_to_file", "replace_file_content", "multi_replace_file_content"}

# Python interpreter runner pattern — for python invocations we only examine
# interpreter + script path, NOT the CLI arguments (which may legitimately contain
# dangerous strings as test data, documentation, or --test-cmd payloads).
_PYTHON_RUNNER_RE = re.compile(r"(?i)^(python3?\.?\d*|py\.?\d*)\s+")

# Critical patterns — matched against the EFFECTIVE COMMAND only (not quoted args).
# These operations ALWAYS produce force_ask and cannot be bypassed via the DB.
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
    # Database destruction
    (r"(?i)\bDROP\s+(DATABASE|SCHEMA)\b",                         "Database schema drop"),
    (r"(?i)\bTRUNCATE\s+TABLE\b",                                 "Table truncate operation"),
]

# Default safe rules — seeded via INSERT OR IGNORE (idempotent, never duplicates).
DEFAULT_SAFE_RULES = [
    # ── Git workflow ─────────────────────────────────────────────────────────
    ("git status*",              "run_command", "always", "Standard status check"),
    ("git diff*",                "run_command", "always", "Standard diff inspection"),
    ("git log*",                 "run_command", "always", "Standard commit log"),
    ("git show*",                "run_command", "always", "Standard commit inspection"),
    ("git add*",                 "run_command", "always", "Staging files for commit"),
    ("git commit*",              "run_command", "always", "Committing staged changes"),
    ("git push",                 "run_command", "always", "Standard git push"),
    ("git push origin *",        "run_command", "always", "Pushing to remote origin (non-force)"),
    ("git push -u origin *",     "run_command", "always", "Setting upstream and pushing (non-force)"),
    ("git pull*",                "run_command", "always", "Pulling updates from remote"),
    ("git fetch*",               "run_command", "always", "Fetching remote references"),
    ("git checkout *",           "run_command", "always", "Branch switching or creation"),
    ("git switch *",             "run_command", "always", "Branch switching"),
    ("git branch*",              "run_command", "always", "Branch listing or creation"),
    ("git stash*",               "run_command", "always", "Working state stashing"),
    ("git merge*",               "run_command", "always", "Branch merging"),
    ("git tag*",                 "run_command", "always", "Tag operations"),
    ("git remote*",              "run_command", "always", "Remote management"),
    ("git config*",              "run_command", "always", "Git config"),
    ("git ls-files*",            "run_command", "always", "Listing tracked files"),
    # ── Python / script execution ────────────────────────────────────────────
    ("python *",                 "run_command", "always", "Running python script"),
    ("python3 *",                "run_command", "always", "Running python3 script"),
    ("py *",                     "run_command", "always", "Running python via py launcher"),
    ("python -m *",              "run_command", "always", "Running python module"),
    ("python3 -m *",             "run_command", "always", "Running python3 module"),
    # ── Package / build tools ────────────────────────────────────────────────
    ("uv *",                     "run_command", "always", "Running uv"),
    ("pip *",                    "run_command", "always", "Running pip"),
    ("pip3 *",                   "run_command", "always", "Running pip3"),
    ("npm *",                    "run_command", "always", "Running npm"),
    ("npx *",                    "run_command", "always", "Running npx"),
    ("node *",                   "run_command", "always", "Running node"),
    ("yarn *",                   "run_command", "always", "Running yarn"),
    ("pnpm *",                   "run_command", "always", "Running pnpm"),
    # ── Linters / formatters / type checkers ────────────────────────────────
    ("ruff *",                   "run_command", "always", "Running ruff"),
    ("mypy *",                   "run_command", "always", "Running mypy"),
    ("black *",                  "run_command", "always", "Running black formatter"),
    ("flake8 *",                 "run_command", "always", "Running flake8"),
    ("eslint *",                 "run_command", "always", "Running eslint"),
    ("prettier *",               "run_command", "always", "Running prettier"),
    ("tsc *",                    "run_command", "always", "Running TypeScript compiler"),
    # ── Test runners ────────────────────────────────────────────────────────
    ("pytest*",                  "run_command", "always", "Running pytest"),
    ("python -m unittest*",      "run_command", "always", "Running unit tests"),
    ("npm test*",                "run_command", "always", "Running npm test"),
    ("npm run *",                "run_command", "always", "Running npm script"),
    # ── Shell inspection ────────────────────────────────────────────────────
    ("dir*",                     "run_command", "always", "Directory listing (Windows)"),
    ("ls*",                      "run_command", "always", "Directory listing"),
    ("cat *",                    "run_command", "always", "File content display"),
    ("type *",                   "run_command", "always", "File content display (Windows)"),
    ("echo *",                   "run_command", "always", "Echo output"),
    ("where *",                  "run_command", "always", "Locating executable"),
    ("which *",                  "run_command", "always", "Locating executable"),
    # ── File mutation tools — always safe ───────────────────────────────────
    ("*", "write_to_file",             "always", "Standard file write"),
    ("*", "replace_file_content",      "always", "Standard file edit/replace"),
    ("*", "multi_replace_file_content","always", "Standard multi-edit/replace"),
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
    """Creates tables and upserts all default rules. Fully idempotent."""
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
                    blast_score REAL,
                    is_destructive REAL,
                    decision TEXT,
                    source TEXT,
                    reason TEXT
                )
            """)
            # Explicit '' for conversation_id/workspace_path so UNIQUE deduplicates correctly
            # (SQL NULL != NULL, so NULLs would bypass the uniqueness check).
            for pattern, tool, scope, reason in DEFAULT_SAFE_RULES:
                conn.execute("""
                    INSERT OR IGNORE INTO rules
                        (pattern, tool_name, scope, conversation_id, workspace_path, decision, reason)
                    VALUES (?, ?, ?, '', '', 'allow', ?)
                """, (pattern, tool, scope, reason))
    finally:
        conn.close()


def _extract_check_string(tool_name: str, command: str) -> str:
    """
    Returns the portion of the command string to check against CRITICAL_PATTERNS.

    - Strips 'cmd /c' wrappers and surrounding quotes.
    - For compound commands (&&, ||, |): examines only the first sub-command.
    - For Python invocations: only checks interpreter + script path, NOT CLI arguments
      (arguments may legitimately contain dangerous strings as test data / --test-cmd payloads).
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
    Returns (True, reason) if the operation is inherently critical (always force_ask).
    File write tools always return (False, '') — their serialized args may contain
    dangerous strings in CodeContent/documentation but no shell command is executed.
    """
    if tool_name in SKIP_CRITICAL_TOOLS:
        return False, ""

    check_str = _extract_check_string(tool_name, command)
    for pattern, description in CRITICAL_PATTERNS:
        if re.search(pattern, check_str):
            return True, description
    return False, ""


def clean_command_string(command: str) -> str:
    """Strips cmd /c wrappers and surrounding quotes for display / DB pattern matching."""
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
    reason: str = "",
) -> bool:
    """Saves an approval/denial rule. Rejects saving 'allow' for critical patterns."""
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
    blast_score: float,
    is_destructive_val: float,
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
                        (conversation_id, tool_name, command, blast_score, is_destructive,
                         decision, source, reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (conversation_id, tool_name, command[:500],
                      blast_score, is_destructive_val, decision, source, reason))
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


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Antigravity Jev Safety Gate Decision Database")
    parser.add_argument("--list",          action="store_true")
    parser.add_argument("--allow",         type=str)
    parser.add_argument("--tool",          type=str, default="run_command")
    parser.add_argument("--scope",         choices=["always", "session"], default="always")
    parser.add_argument("--conversation",  type=str, default="")
    parser.add_argument("--reason",        type=str, default="User specified rule")
    parser.add_argument("--init-defaults", action="store_true")
    parser.add_argument("--test-cmd",      type=str)
    args = parser.parse_args()

    if args.init_defaults:
        init_db()
        print(f"[+] Decision database seeded: {get_db_path()}")
        sys.exit(0)

    if args.allow:
        try:
            save_decision(args.allow, tool_name=args.tool, scope=args.scope,
                          conversation_id=args.conversation or None, reason=args.reason)
            print(f"[+] Saved '{args.allow}' ({args.scope}) for tool '{args.tool}'.")
        except ValueError as e:
            print(f"[-] Failed: {e}")
        sys.exit(0)

    if args.test_cmd:
        crit, crit_r = is_critical(args.tool, args.test_cmd)
        chk = _extract_check_string(args.tool, args.test_cmd)
        dec, dec_r = check_decision(args.tool, args.test_cmd, args.conversation)
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
