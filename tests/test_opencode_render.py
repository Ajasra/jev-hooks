"""RFC-27 S2: the generated OpenCode plugin and config track the shared registry."""

from __future__ import annotations

import json
import re
from pathlib import Path

from jev.contracts import EventKind
from jev.install.render import (
    OPENCODE_DRAIN_HOOK,
    OPENCODE_PRE_FILTER,
    opencode_config,
    opencode_plugin,
    opencode_subscriptions,
    opencode_timeouts,
)
from jev.registry import FEATURES

GOLDEN = Path(__file__).parent / "fixtures" / "opencode" / "jev.ts"

HOOK_OF_KIND = {
    EventKind.TURN_BEFORE: "chat.message",
    EventKind.TOOL_BEFORE: "tool.execute.before",
    EventKind.TOOL_AFTER: "tool.execute.after",
    EventKind.CONTEXT_CHECKPOINT: "experimental.session.compacting",
}


def block(source: str, signature: str) -> str:
    start = source.index(signature)
    return source[start : source.index("\n}", start)]


def pairs(text: str) -> dict[str, str]:
    found = re.findall(r'"([^"]+)": ("[^"]*"|\d+)', text)
    return {key: value[1:-1] if value.startswith('"') else value for key, value in found}


def test_rendered_plugin_matches_the_committed_snapshot():
    assert opencode_plugin() == GOLDEN.read_text(encoding="utf-8")


def test_subscriptions_track_the_feature_registry():
    source = opencode_plugin()
    rendered = pairs(block(source, "const HOOKS"))
    claimed = {kind for feature in FEATURES for kind in feature.triggers}
    for kind, hook in HOOK_OF_KIND.items():
        if kind in claimed:
            assert hook in rendered, f"feature claims {kind.value} but {hook} is not subscribed"
    assert rendered == opencode_subscriptions()
    assert rendered["experimental.session.compacting"] == "context.checkpoint"
    assert OPENCODE_DRAIN_HOOK in source
    assert "event" not in rendered
    assert "experimental.chat.system.transform" not in rendered


def test_timeouts_track_secure_failure_policies():
    source = opencode_plugin()
    rendered = {name: int(value) for name, value in pairs(block(source, "const SPAWN_TIMEOUT")).items()}
    secure = {
        kind
        for feature in FEATURES
        if feature.failure_policy == "secure"
        for kind in feature.triggers
    }
    kind_of_hook = {hook: kind for kind, hook in HOOK_OF_KIND.items()}
    for hook, timeout in rendered.items():
        expected = 1000 if kind_of_hook[hook] in secure else 750
        assert timeout == expected, f"{hook} renders {timeout}ms for a {kind_of_hook[hook].value} hook"
    assert rendered == opencode_timeouts()
    assert rendered["tool.execute.before"] == 1000


def test_pre_filter_matches_the_fast_path_tool_list():
    source = opencode_plugin()
    line = next(item for item in source.splitlines() if "PRE_FILTER = new Set" in item)
    rendered = re.findall(r'"([^"]+)"', line)
    assert rendered == list(OPENCODE_PRE_FILTER)
    assert rendered == [
        "read", "glob", "grep", "list", "lsp", "skill", "todowrite", "question", "webfetch", "websearch",
    ]
    assert "if (PRE_FILTER.has(name)) return" in source


def test_plugin_lifecycle_contract_is_present():
    source = opencode_plugin()
    lines = source.splitlines()
    assert lines[0].startswith("// @jev-owned")
    assert "export default {" in source
    assert 'id: "jev"' in source
    assert "async server(input: any)" in source
    assert '["-m", "jev", "doctor", "--cwd", directory]' in source
    assert '["-m", "jev", "hook", "--harness", "opencode"]' in source
    assert 'input: JSON.stringify(payload)' in source
    assert 'const PRE_FILTER = new Set(' in source
    assert 'hook: hook' in source
    assert 'harness_version: HARNESS_VERSION' in source
    assert 'session_id: session' in source
    assert 'turn_id: turn' in source
    assert 'agent: agent' in source
    assert 'prompt: prompt' in source
    assert 'native: native || {}' in source
    assert 'payload.result = {' in source
    assert "checkpoint_context" in source
    assert 'result.decision === "deny"' in source
    assert 'result.decision === "ask"' in source
    assert "error.jev === true" in source
    assert "parts[index].text = parts[index].text" in source
    assert "enqueue(session, result.context)" in source
    assert "output.output + \"\\n\" + bound(" in source
    assert "target.push(item)" in source
    assert "system.indexOf(tail) >= 0" in source
    assert "ETIMEDOUT" in source
    assert "JSON.parse(String(raw.stdout" in source
    assert "return undefined" in source
    assert not any(line.startswith("throw ") for line in lines)
    assert source.count("try {") >= 6


def test_spawn_arguments_survive_windows_paths():
    source = opencode_plugin(python=r"D:\01_GIT\Jev\.venv\Scripts\python.exe", harness_version="1.18.33")
    python = re.search(r'const PYTHON = (".*")', source).group(1)
    version = re.search(r'const HARNESS_VERSION = (".*")', source).group(1)
    assert json.loads(python) == r"D:\01_GIT\Jev\.venv\Scripts\python.exe"
    assert json.loads(version) == "1.18.33"


def test_opencode_config_declares_the_owned_keys():
    config = opencode_config(python="/repo/.venv/bin/python", skills_path="/repo/.agents/skills")
    assert config["mcp"]["jev"] == {
        "type": "local",
        "command": ["/repo/.venv/bin/python", "-m", "jev", "mcp", "--cwd", ".", "--harness", "opencode"],
        "enabled": True,
    }
    assert config["skills"] == {"paths": ["/repo/.agents/skills"]}
    assert "skills" not in opencode_config()
