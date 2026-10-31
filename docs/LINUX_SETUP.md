# Linux global setup

Install one Jev runtime and connect Codex, Antigravity, and OpenCode to it. These instructions describe the Linux configuration; native Linux app acceptance is still pending. Windows verification does not establish Linux acceptance.

For the current OpenCode revalidation run, follow [Linux OpenCode acceptance](LINUX_OPENCODE_ACCEPTANCE.md). It covers the Linux tests, live smoke matrix, and receipt expected by RFC-27.

## Install the shared runtime

Use a stable checkout path. From that checkout, with Python 3.10 or newer:

```bash
python3 -m venv .venv-linux
.venv-linux/bin/python -m pip install -e '.[mcp]'
.venv-linux/bin/python -m jev doctor --cwd .
realpath .venv-linux/bin/python
pwd -P
```

Record the absolute interpreter and checkout paths. In the snippets below, replace `/absolute/path/Jev` with your checkout path. Keep this virtual environment separate from a Windows environment. GUI apps may not inherit your terminal's activated environment, so registrations use the absolute interpreter.

Configure provider credentials following the [user guide](USER_GUIDE.md#step-2-configure-provider-api-key-in-env). A Jev checkout `.env` is not automatically a credential source for unrelated workspaces. Provide credentials through the app's environment or that workspace's supported environment file. Missing provider credentials leave semantic evaluation unavailable; deterministic safety still runs.

Back up existing harness configuration files before editing. Merge Jev's entries into their existing objects, preserving other servers, hooks, and skills.

## Codex

Register the user-global MCP server:

```bash
codex mcp add jev -- /absolute/path/Jev/.venv-linux/bin/python -m jev mcp --cwd . --harness codex
codex mcp get jev
```

Merge the following event entries into `~/.codex/hooks.json`, under its `hooks` object. Append to existing event arrays; replace an older Jev registration rather than duplicating it. Linux uses `command`, without `cmd /c` or a Windows launcher.

```json
{
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "command": "'/absolute/path/Jev/.venv-linux/bin/python' -m jev hook --harness codex", "timeout": 5}]}],
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "'/absolute/path/Jev/.venv-linux/bin/python' -m jev hook --harness codex", "timeout": 5, "additionalContextLimit": 12000}]}],
    "PreToolUse": [{"matcher": "Bash|apply_patch|mcp__.*", "hooks": [{"type": "command", "command": "'/absolute/path/Jev/.venv-linux/bin/python' -m jev hook --harness codex", "timeout": 5}]}]
  }
}
```

Review and trust the new hooks when Codex prompts, then start a fresh chat. The Jev checkout also contains repository-local Codex hooks. Before using that checkout with global hooks, arrange a thin global dispatcher to return `{}` when the payload's resolved `cwd` equals the Jev checkout, matching the Windows setup described in the [user guide](USER_GUIDE.md#b-openai-codex-setup). Otherwise Jev can run twice. Test global acceptance first in a separate project.

Jev's MCP skill catalog includes its canonical package skills. To expose those skills to Codex's native discovery globally, link each missing skill directory into `~/.agents/skills/`; preserve existing directories with the same name. Do not replace the entire user skills directory.

## Antigravity

Merge this entry into `mcpServers` in `~/.gemini/antigravity/mcp_config.json`:

```json
{
  "jev": {
    "command": "/absolute/path/Jev/.venv-linux/bin/python",
    "args": ["-m", "jev", "mcp", "--cwd", ".", "--harness", "antigravity"],
    "disabled": false
  }
}
```

Merge this entry into `~/.gemini/config/hooks.json`. Do not link the checkout's Windows registration, which invokes `cmd /c`.

```json
{
  "jev-runtime": {
    "enabled": true,
    "PreInvocation": [{"type": "command", "command": "'/absolute/path/Jev/.venv-linux/bin/python' -m jev hook --harness antigravity"}],
    "PreToolUse": [{"matcher": "run_command|write_to_file|replace_file_content|multi_replace_file_content", "hooks": [{"type": "command", "command": "'/absolute/path/Jev/.venv-linux/bin/python' -m jev hook --harness antigravity"}]}]
  }
}
```

Link canonical skills individually into `~/.gemini/config/skills/`, preserving existing names. Link protocols only where they do not replace existing configuration. Reload Antigravity and confirm that your installed Linux version loads these hook registrations; the Windows configuration layout alone is not proof.

## OpenCode

With OpenCode installed and available on `PATH`, run from the Jev checkout:

```bash
.venv-linux/bin/python -m jev install opencode --cwd .
.venv-linux/bin/python -m jev doctor --cwd .
opencode mcp list
```

The installer uses `$XDG_CONFIG_HOME/opencode`, or `~/.config/opencode` when that variable is unset. It records the Linux interpreter, merges Jev's MCP and skill entries, and generates `plugins/jev.ts`. Do not copy the Windows-generated plugin. If the installer refuses an existing file, inspect the reported ownership or JSONC conflict before changing it.

Restart OpenCode after installation.

## Verify from each app

Open a separate project, then ask each harness:

> Call Jev's diagnostics_status and skills_list. Report the harness identity, workspace root, problems, and skill count. Run a harmless shell command, then inspect Jev's audit records to confirm the hook ran.

Expect `codex`, `antigravity`, or `opencode` as the identity, the actual project as the workspace root, and the seven canonical Jev skills plus any project skills. An app-directory workspace root needs correction before relying on project knowledge or lint rules. MCP startup alone does not verify lifecycle hooks.

From the terminal, inspect the corresponding audit records:

```bash
/absolute/path/Jev/.venv-linux/bin/python -m jev stats --harness codex
/absolute/path/Jev/.venv-linux/bin/python -m jev stats --harness antigravity
/absolute/path/Jev/.venv-linux/bin/python -m jev stats --harness opencode
```

Confirm a new safety evaluation for the harmless command. Do not use a destructive command as an installation test. Keep the checkout and virtual environment in place: editable installs, skill links, and launch registrations reference them.
