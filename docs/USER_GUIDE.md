# Jev Shared Runtime: User Guide

> **Audience**: developers using Google Antigravity or OpenAI Codex
>
> **Status**: implemented locally
>
> **Supported platform**: Windows, Python 3.10+

## 1. Problem

Agent harnesses expose different lifecycle JSON and approval behavior. Copying Jev logic into separate integrations would make safety policy, skill routing, and knowledge retrieval diverge.

## 2. Inspiration

The runtime treats each harness as a transport. Both translate into one internal event contract and use the same decisions, storage, and feature catalog.

## 3. Solution

Install one Python package. Antigravity and Codex then call the same `jev` command. Repository skills stay canonical in `.agents/skills`; audit records retain a `harness` field and can be viewed separately.

## 4. Example

When either harness proposes `git reset --hard`, the shared invariant shield denies it before any network request. Routine commands such as `git status` pass after deterministic checks. If the TypeSafe service is unavailable, optional routing context is omitted and deterministic safety remains active.

## 5. Compatibility at a glance

The core implementation is shared. Each harness contributes only event translation and output encoding.

| Capability | Antigravity | Codex | Shared implementation |
| --- | --- | --- | --- |
| Safety policy | `PreToolUse` | `PreToolUse` | `core/safety.py`; deterministic invariants always deny in both harnesses. |
| Advisory context | `PreInvocation` | `SessionStart` and `UserPromptSubmit` | `core/speculative.py` and `core/knowledge.py`. |
| Skill selection | Full body or soft-hint injection | Catalog ranking without body injection; Codex retains native skill discovery | `core/skills.py` reads `.agents/skills`. |
| Knowledge retrieval | Advisory context at pre-invocation | Advisory context at session and prompt boundaries | `core/knowledge.py` reads `.agents/knowledge`. |
| Callable tools | Configure the Jev stdio MCP server when the harness supports MCP | Registered through Codex MCP configuration | `tooling.py`, `registry.py`, and `transports/mcp.py`. |
| Audit and rules | `antigravity_events` view | `codex_events` view | One `jev.sqlite3` database with a harness field. |
| Transcript compaction | Explicit sidecar checkpoint | Explicit sidecar checkpoint | `core/compaction.py`; it does not rewrite either harness transcript. |

Codex maps a conditional safety result to a denial because its `PreToolUse` hook cannot request a native approval. Native harness and sandbox approvals still apply after Jev allows an operation.

## 6. Install for this repository

From the repository root:

```cmd
cmd /c python -m pip install --user -e ".[mcp]"
cmd /c python -m jev doctor --cwd .
```

The editable installation makes `python -m jev` available when Codex launches project hooks and its MCP server. It also lets Antigravity wrappers import the same package source. Use the same `python` executable for installation and for Codex; `cmd /c python -c "import sys; print(sys.executable)"` displays it.

Configure one provider in your user environment or harness environment:

```cmd
cmd /c setx TYPESAFE_API_KEY "your-typesafe-key"
```

Or:

```cmd
cmd /c setx OPENROUTER_API_KEY "your-openrouter-key"
```

Optional overrides are `TYPESAFE_ENDPOINT`, `JEV_MODEL`, `JEV_DATA_ROOT`, and `JEV_DB_PATH`. Project `jev.json` may configure skill roots, knowledge roots, context budget, and semantic timeout. It cannot redirect trusted rule storage or weaken safety policy.

## 7. Enable Codex for this repository

The repository includes [`.codex/hooks.json`](../.codex/hooks.json) for `SessionStart`, `UserPromptSubmit`, and `PreToolUse`. After installing the package, restart Codex and review/trust the project hook definition when prompted.

> [!NOTE]
> **Harness Approval & Error Handling Differences**:
> - **Google Antigravity**: Supports interactive confirmation modals (`"decision": "force_ask"` or `"ask"`). If an operation requires developer review or encounters an inspection glitch, Antigravity renders a confirmation dialog in the IDE allowing you to allow or deny it with one click. File edits (`write_to_file`, `replace_*`) always fail open so editing code is never blocked by hook inspection issues.
> - **OpenAI Codex**: Hooks at `PreToolUse` support only `allow` or `deny` without an interactive modal. Jev therefore maps conditional reviews to a clean denial with actionable reasoning, which can be retried or authorized via `jev authorize`.

## 8. Enable Antigravity

Link the canonical sources into Antigravity's global configuration:

```cmd
cmd /c mklink /J "%USERPROFILE%\.gemini\config\hooks" "%CD%\.agents\hooks"
cmd /c mklink /J "%USERPROFILE%\.gemini\config\skills" "%CD%\.agents\skills"
cmd /c mklink /J "%USERPROFILE%\.gemini\config\protocols" "%CD%\.agents\protocols"
cmd /c mklink "%USERPROFILE%\.gemini\config\hooks.json" "%CD%\.agents\hooks.json"
```

Reload Antigravity after creating the links. Its legacy `jev_safety_gate.py` entry point delegates to the shared runtime for compatibility.

## 9. Data and Logs

The default Windows database is `%LOCALAPPDATA%\Jev\jev.sqlite3`. It contains:

- `events`: all feature decisions with harness, workspace, session, and tool identity.
- `codex_events`: a view containing Codex records.
- `antigravity_events`: a view containing Antigravity records.
- `rules`: harness-scoped policy memory and one-use authorizations.
- `invocations`: atomic deduplication claims and replayable decisions.
- `session_context` and `feedback`: isolated context and exact event feedback.

Prompts and commands are not stored in full by default. Diagnostic details are bounded and secret-like values are redacted.

Run the compatibility database view:

```cmd
cmd /c python .agents\hooks\safety_db.py --review --harness codex
cmd /c python .agents\hooks\safety_db.py --review --harness antigravity
```

## 10. One-Use Authorization

Invariant operations such as force push, recursive forced deletion, hard reset, disk formatting, and database destruction cannot be authorized through Jev.

For a conditionally denied operation, use the manual two-step CLI outside the agent tool surface:

```cmd
cmd /c jev authorize --harness codex --tool Bash --command "your command" --workspace-id WORKSPACE_ID
```

The command prints an operation digest and saves nothing. Review the operation, then repeat with the displayed digest:

```cmd
cmd /c jev authorize --harness codex --tool Bash --command "your command" --workspace-id WORKSPACE_ID --confirm-digest DIGEST
```

The grant is consumed atomically on the matching tool attempt. Native harness approvals and sandbox rules still apply.

## 11. Skills, Knowledge, and Tools

Add repository skills under `.agents/skills/<name>/SKILL.md`. Both harnesses discover the same source; Jev can also rank it for progressive disclosure.

Knowledge items live under `.agents/knowledge`. Automatic reads are advisory. Writes occur only through explicit `knowledge_learn` tool calls.

Install the optional MCP dependency to expose the shared tool registry:

```cmd
cmd /c python -m pip install --user -e ".[mcp]"
cmd /c python -m jev mcp --cwd .
```

Codex reads the repository [`.codex/config.toml`](../.codex/config.toml) and launches this server for trusted projects. Antigravity can register the same `python -m jev mcp --cwd .` stdio command when its MCP configuration is enabled. The current tools are `knowledge_search`, `knowledge_learn`, `skills_list`, and `diagnostics_status`.

## 12. New-machine and global Codex setup

These steps install Jev for one Windows user. They do not modify the system Python, so no administrator account is required.

1. Clone this repository and open a terminal at its root.
2. Confirm which interpreter Codex should use:

   ```cmd
   cmd /c python -c "import sys; print(sys.executable)"
   ```

3. Install Jev and its MCP dependency into that user environment:

   ```cmd
   cmd /c python -m pip install --user -e ".[mcp]"
   cmd /c python -m jev doctor --cwd .
   ```

4. Enable project hooks by opening the repository as a trusted Codex project, then restart Codex and accept its hook review. Project configuration is loaded only for trusted projects.
5. To expose the Jev MCP tools in all Codex projects, add this block to `%USERPROFILE%\.codex\config.toml`. Preserve any existing configuration and MCP servers.

   ```toml
   [mcp_servers.jev]
   command = "python"
   args = ["-m", "jev", "mcp"]
   startup_timeout_sec = 10
   tool_timeout_sec = 30
   ```

   Do not set a global `cwd`: Codex starts the server in the active project so Jev can use that repository's `.agents/skills`, `.agents/knowledge`, and `jev.json` configuration.

6. Restart Codex, then verify the global registration:

   ```cmd
   cmd /c codex mcp list
   ```

   Start a new Codex task and ask it to use `diagnostics_status`, then `skills_list`. New tasks reload their MCP tool catalog.

Global MCP registration exposes the tools, while lifecycle hooks remain project-scoped by default. To enforce the same hooks for every local project, merge the `hooks` object from [`.codex/hooks.json`](../.codex/hooks.json) into `%USERPROFILE%\.codex\hooks.json`; do not overwrite an existing user hook file.

Provider keys are optional for deterministic safety, tools, and local knowledge. Set `TYPESAFE_API_KEY` or `OPENROUTER_API_KEY` only when you want semantic skill, knowledge, or speculative ranking.

## 13. Verify

The default suite is offline and uses isolated temporary databases:

```cmd
cmd /c python -m pytest -q
```

Live TypeSafe regression tests require an explicit opt-in:

```cmd
cmd /c set JEV_RUN_LIVE_TESTS=1
cmd /c python -m pytest tests\test_speculative_router.py -q
```
