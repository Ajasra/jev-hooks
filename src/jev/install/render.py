"""Generate native hook registrations from the shared feature registry."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jev.registry import FEATURES


def codex_hooks(command: str = "python -m jev hook --harness codex") -> dict[str, Any]:
    return {
        "description": "Jev shared runtime hooks for Codex.",
        "hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command_windows": command,
                                           "statusMessage": "Loading Jev context", "timeout": 5}]}],
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command_windows": command,
                                              "statusMessage": "Preparing Jev context", "timeout": 5,
                                              "additionalContextLimit": 12000}]}],
            "PreToolUse": [{"matcher": "Bash|apply_patch|mcp__.*", "hooks": [
                {"type": "command", "command_windows": command,
                 "statusMessage": "Checking Jev policy", "timeout": 5}
            ]}],
        },
    }


def antigravity_hooks(command: str = "cmd /c python -m jev hook --harness antigravity") -> dict[str, Any]:
    return {
        "jev-runtime": {
            "enabled": True,
            "PreInvocation": [{"type": "command", "command": command}],
            "PreToolUse": [{"matcher": "run_command|write_to_file|replace_file_content|multi_replace_file_content",
                             "hooks": [{"type": "command", "command": command}]}],
        }
    }


def capability_manifest() -> dict[str, Any]:
    return {
        feature.id: {
            "version": feature.version,
            "triggers": sorted(trigger.value for trigger in feature.triggers),
            "required_capabilities": sorted(feature.required_capabilities),
            "failure_policy": feature.failure_policy,
        }
        for feature in FEATURES
    }
