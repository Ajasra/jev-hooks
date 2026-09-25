"""
Integration test covering all previously-failing cases from user screenshots.
"""
import subprocess
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".agents" / "hooks"))

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

print("--- Write / Edit tools (must NEVER be blocked) ---")
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

print("\n--- Python script execution (must NEVER be blocked) ---")
all_pass &= check(
    "python notion_server.py --sync (blast_radius false positive)",
    "run_command",
    {"CommandLine": "cmd /c python .agents/mcp/notion_server.py --sync Calls/2026-09_Waag"},
    "allow"
)
all_pass &= check(
    "python purge_blocks.py (absolute path)",
    "run_command",
    {"CommandLine": r'cmd /c python "C:\Users\user\.gemini\antigravity-ide\brain\scratch\purge_blocks.py"'},
    "allow"
)
all_pass &= check(
    "python safety_db.py --test-cmd containing git reset --hard in args",
    "run_command",
    {"CommandLine": 'cmd /c python .agents/hooks/safety_db.py --test-cmd "cmd /c git reset --hard HEAD~1"'},
    "allow"
)
all_pass &= check(
    "compound python && with dangerous string in quoted arg",
    "run_command",
    {"CommandLine": 'cmd /c python .agents/hooks/safety_db.py --test-cmd "cmd /c rmdir /s /q dist" && echo ---'},
    "allow"
)

print("\n--- Routine git commands (must NEVER be blocked) ---")
all_pass &= check("git commit", "run_command", {"CommandLine": "cmd /c git commit -m 'update'"}, "allow")
all_pass &= check("git push origin", "run_command", {"CommandLine": "cmd /c git push origin main"}, "allow")
all_pass &= check("git status", "run_command", {"CommandLine": "cmd /c git status"}, "allow")
all_pass &= check("git add .", "run_command", {"CommandLine": "cmd /c git add ."}, "allow")

print("\n--- Critical operations (must ALWAYS force_ask) ---")
all_pass &= check("git reset --hard",  "run_command", {"CommandLine": "cmd /c git reset --hard HEAD~1"}, "force_ask")
all_pass &= check("git push --force",  "run_command", {"CommandLine": "cmd /c git push --force"}, "force_ask")
all_pass &= check("rmdir /s /q dist",  "run_command", {"CommandLine": "cmd /c rmdir /s /q dist"}, "force_ask")
all_pass &= check("rm -rf",            "run_command", {"CommandLine": "cmd /c rm -rf ./node_modules"}, "force_ask")

print(f"\n{'All tests PASSED' if all_pass else 'SOME TESTS FAILED'}")
sys.exit(0 if all_pass else 1)
