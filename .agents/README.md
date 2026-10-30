# Shared Agent Configuration

`.agents/` is the canonical repository source for Jev protocols, skills, knowledge, and Antigravity/OpenCode compatibility entry points. Runtime logic lives in `src/jev/` and is shared by Google Antigravity, OpenAI Codex, and OpenCode.

## Layout

```text
.agents/
├── AGENTS.md             workspace rules for both harnesses
├── hooks.json            Antigravity registration
├── hooks/
│   ├── jev_dispatch.py   checkout bootstrap into the shared CLI
│   ├── jev_*             deprecated compatibility entry points
│   └── safety_db.py      compatibility database CLI
├── knowledge/            repository-scoped knowledge items
├── protocols/            architectural and documentation invariants
└── skills/               canonical skill catalog
```

The shared package has the complementary structure:

```text
src/jev/
├── contracts.py          harness-neutral event and result model
├── registry.py           one feature and tool catalog
├── runtime.py            dispatch, replay, and audit orchestration
├── core/                 safety, skills, knowledge, speculation, compaction
├── adapters/             Antigravity and Codex protocol translation
├── services/             configuration, providers, and SQLite storage
└── transports/           MCP and future transport bindings
```

## Rules for new capabilities

Add hook logic once under `src/jev/core/`, then add its `FeatureSpec` to `src/jev/registry.py`. Add callable tool behavior once in `src/jev/tooling.py`, then add its `ToolSpec`; MCP registration is derived from that registry. Add skills only under `.agents/skills/<name>/SKILL.md`.

Compatibility files in `.agents/hooks/` may translate or forward data. They must not contain independent feature policy.

## Harness registrations

Codex uses [`.codex/hooks.template.json`](../.codex/hooks.template.json), installed once into the user's Codex configuration by [`scripts/codex_hooks.py`](../scripts/codex_hooks.py). The checked-in [`.codex/hooks.json`](../.codex/hooks.json) stays empty, and project `.codex/config.toml` must not define a Jev MCP server. Codex loads matching user and project hooks together, so a project Jev registration would dispatch twice. Run the check from this checkout to confirm the active project has no duplicate:

```sh
python scripts/codex_hooks.py check
```

Antigravity uses [`hooks.json`](hooks.json), normally linked into its global configuration. On Windows, the full user-scope setup for Antigravity, Codex, and OpenCode is:

```cmd
powershell -ExecutionPolicy Bypass -File scripts\install-user-harnesses.ps1
```

Install the editable package once per device from the repository root, then install and check Codex's user configuration:

```cmd
python -m pip install --user -e ".[mcp]"
python scripts\codex_hooks.py install
python scripts\codex_hooks.py check
jev doctor --cwd .
```

Use separate Git checkouts on separate devices. Commit and push source changes from one checkout; fast-forward the others and rerun the installer when harness templates change. Do not copy generated user configuration, hook trust state, or the SQLite database through Git.

## Persistence

Jev uses one SQLite database, defaulting to `%LOCALAPPDATA%\Jev\jev.sqlite3`. Every record includes its harness identity. The `codex_events` and `antigravity_events` views provide separate logs without separate schemas or policy stores.

Read [the architecture specification](../docs/ARCHITECTURE.md) for contracts and invariants, and [the user guide](../docs/USER_GUIDE.md) for installation and operation.
