"""
Integration test suite for Jev Safety Gate:
- File editing tools fast-path & sensitive path protection
- Routine dev operations evaluated by Jev intent scoring (without hardcoded allowlists)
- Invariant critical shield for catastrophic commands
- User decision memory (SQLite persistence)
"""
import subprocess
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".agents" / "hooks"))
from safety_db import save_decision, clear_all_rules

GATE = ["python", ".agents/hooks/jev_safety_gate.py"]
CWD = "d:/01_GIT/Jev"


def run_gate(tool_name, args_dict, conv_id="test-123"):
    payload = json.dumps({
        "toolCall": {"name": tool_name, "args": args_dict},
        "conversationId": conv_id,
        "workspacePaths": [CWD]
    })
    r = subprocess.run(GATE, input=payload.encode(), capture_output=True, cwd=CWD)
    try:
        return json.loads(r.stdout.decode().strip())
    except Exception:
        return {"decision": "ERROR", "raw": r.stdout.decode()}


def check(label, tool, args_dict, expected):
    out = run_gate(tool, args_dict)
    decision = out.get("decision", "ERROR")
    status = "PASS" if decision == expected else "FAIL"
    print(f"  [{status}] [{decision:>10}]  {label}")
    return decision == expected


all_pass = True

print("--- File Editing Tools (workspace files allowed, sensitive paths guarded) ---")
all_pass &= check(
    "write_to_file with rmdir /s in CodeContent (false positive fix)",
    "write_to_file",
    {"TargetFile": "d:/01_GIT/Jev/proposals/04_PROPOSAL_D.md",
     "CodeContent": "# rmdir /s and git reset --hard mentioned in docs"},
    "allow"
)
all_pass &= check(
    "write_to_file test file with dangerous arg strings",
    "write_to_file",
    {"TargetFile": "d:/01_GIT/Jev/tests/test_gate_integration.py",
     "CodeContent": 'cmd /c git reset --hard HEAD~1'},
    "allow"
)
all_pass &= check(
    "replace_file_content (README)",
    "replace_file_content",
    {"TargetFile": "d:/01_GIT/Jev/README.md", "TargetContent": "x", "ReplacementContent": "y"},
    "allow"
)
all_pass &= check(
    "multi_replace_file_content",
    "multi_replace_file_content",
    {"TargetFile": "d:/01_GIT/Jev/README.md"},
    "allow"
)
all_pass &= check(
    "write_to_file on sensitive SSH key (must force_ask)",
    "write_to_file",
    {"TargetFile": "C:/Users/user/.ssh/id_rsa", "CodeContent": "MALICIOUS KEY"},
    "force_ask"
)

print("\n--- Python & Modern Tool Execution (evaluated via Jev intent scoring) ---")
all_pass &= check(
    "python notion_server.py --sync",
    "run_command",
    {"CommandLine": "cmd /c python .agents/mcp/notion_server.py --sync Calls/2026-09_Waag"},
    "allow"
)
all_pass &= check(
    "python safety_db.py --test-cmd containing dangerous arg string",
    "run_command",
    {"CommandLine": 'cmd /c python .agents/hooks/safety_db.py --test-cmd "cmd /c git reset --hard HEAD~1"'},
    "allow"
)
all_pass &= check(
    "pytest tests/",
    "run_command",
    {"CommandLine": "cmd /c pytest tests/"},
    "allow"
)
all_pass &= check(
    "npm run build",
    "run_command",
    {"CommandLine": "cmd /c npm run build"},
    "allow"
)
all_pass &= check(
    "cargo build --release",
    "run_command",
    {"CommandLine": "cmd /c cargo build --release"},
    "allow"
)

print("\n--- Routine Git Commands (evaluated via Jev intent scoring) ---")
all_pass &= check("git commit", "run_command", {"CommandLine": "cmd /c git commit -m 'update'"}, "allow")
all_pass &= check("git push origin", "run_command", {"CommandLine": "cmd /c git push origin main"}, "allow")
all_pass &= check("git status", "run_command", {"CommandLine": "cmd /c git status"}, "allow")
all_pass &= check("git add .", "run_command", {"CommandLine": "cmd /c git add ."}, "allow")

print("\n--- Invariant Critical Shield (always force_ask, zero LLM bypass) ---")
all_pass &= check("git reset --hard",  "run_command", {"CommandLine": "cmd /c git reset --hard HEAD~1"}, "force_ask")
all_pass &= check("git push --force",  "run_command", {"CommandLine": "cmd /c git push --force"}, "force_ask")
all_pass &= check("rmdir /s /q dist",  "run_command", {"CommandLine": "cmd /c rmdir /s /q dist"}, "force_ask")
all_pass &= check("rm -rf",            "run_command", {"CommandLine": "cmd /c rm -rf ./node_modules"}, "force_ask")

print("\n--- User Decision Memory (SQLite DB) ---")
save_decision("custom_tool_abc*", tool_name="run_command", scope="always", decision="allow", reason="User approved")
all_pass &= check("custom tool permitted by user memory", "run_command", {"CommandLine": "custom_tool_abc --flag"}, "allow")
clear_all_rules()

print(f"\n{'All tests PASSED' if all_pass else 'SOME TESTS FAILED'}")
sys.exit(0 if all_pass else 1)
