import subprocess, json, sys

def test_gate(tool_name, command, conv_id="test-123"):
    payload = json.dumps({
        "toolCall": {"name": tool_name, "args": {"CommandLine": command}},
        "conversationId": conv_id,
        "workspacePaths": ["d:/01_GIT/Jev"]
    })
    result = subprocess.run(
        ["python", ".agents/hooks/jev_safety_gate.py"],
        input=payload.encode(),
        capture_output=True,
        cwd="d:/01_GIT/Jev"
    )
    stdout = result.stdout.decode().strip()
    try:
        out = json.loads(stdout)
        decision = out.get("decision")
    except Exception:
        decision = stdout
    print(f"[{decision:>10}]  {tool_name}: {command[:60]}")
    return out

cases = [
    ("run_command",         "cmd /c git commit -m 'update hooks'"),
    ("run_command",         "cmd /c git push origin main"),
    ("run_command",         "cmd /c git status"),
    ("run_command",         "cmd /c git push --force"),
    ("run_command",         "cmd /c git reset --hard HEAD~1"),
    ("run_command",         "cmd /c rmdir /s /q dist"),
    ("write_to_file",       '{"TargetFile": "test.py"}'),
    ("replace_file_content", '{"TargetFile": "main.py"}'),
]

for tool, cmd in cases:
    test_gate(tool, cmd)
