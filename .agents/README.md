# Shared Agent Configuration

`.agents/` is the canonical repository source for Jev protocols, skills, knowledge, and Antigravity compatibility entry points. Runtime logic lives in `src/jev/` and is shared by Google Antigravity and OpenAI Codex.

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

Codex uses [`.codex/hooks.json`](../.codex/hooks.json). Antigravity uses [`hooks.json`](hooks.json), normally linked into its global configuration:

```cmd
cmd /c mklink /J "%USERPROFILE%\.gemini\config\hooks" "%CD%\.agents\hooks"
cmd /c mklink /J "%USERPROFILE%\.gemini\config\skills" "%CD%\.agents\skills"
cmd /c mklink /J "%USERPROFILE%\.gemini\config\protocols" "%CD%\.agents\protocols"
cmd /c mklink "%USERPROFILE%\.gemini\config\hooks.json" "%CD%\.agents\hooks.json"
```

Install the package once from the repository root so both registrations resolve the same runtime:

```cmd
cmd /c python -m pip install -e .
cmd /c jev doctor --cwd .
```

## Persistence

Jev uses one SQLite database, defaulting to `%LOCALAPPDATA%\Jev\jev.sqlite3`. Every record includes its harness identity. The `codex_events` and `antigravity_events` views provide separate logs without separate schemas or policy stores.

Read [the architecture specification](../docs/ARCHITECTURE.md) for contracts and invariants, and [the user guide](../docs/USER_GUIDE.md) for installation and operation.
