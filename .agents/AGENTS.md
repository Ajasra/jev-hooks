# TypeSafe AI Jev Workspace Rules

These rules apply when working inside the **Jev** repository as a TypeSafe AI systems and hook architect.

## Core protocols

Follow the canonical protocols in [`.agents/protocols/`](protocols/):

- [System One balance](protocols/system-one-balance-protocol.md): keep semantic advice fast, calibrated, and non-blocking while deterministic safety remains authoritative.
- [Documentation standard](protocols/documentation-standard-protocol.md): separate user and developer material, keep the root README concise, and use the unified RFC taxonomy.

## Shared harness architecture

Treat `src/jev/` as the only implementation root for runtime behavior.

- `contracts.py` defines harness-neutral events and results.
- `registry.py` is the extension surface for hook features and callable tools.
- `core/` owns safety, skills, knowledge, speculation, and compaction.
- `adapters/` translates Google Antigravity, OpenAI Codex, and OpenCode protocols.
- `services/storage.py` owns shared SQLite persistence and harness-specific views.
- `.agents/hooks/jev_dispatch.py` is the Antigravity checkout bootstrap.
- `.codex/hooks.template.json` is the Codex user-scope registration template.
- `.codex/hooks.json` stays empty; `.codex/config.toml` must not define Jev MCP at project scope.
- `scripts/codex_hooks.py` is the portable Codex user-scope installer and scope checker.
- `install/opencode.py` merges Jev-owned keys into the OpenCode global config and writes the registry-generated `plugins/jev.ts` shim.
- Harness configuration is generated per device from tracked templates; never commit user config, trust state, or the user SQLite database.

Files named `jev_safety_gate.py`, `jev_skill_router.py`, `jev_speculative_router.py`, `jev_ki_engine.py`, and `jev_compactor.py` are compatibility entry points only. Do not put feature logic in them.

## Extension rules

- Add a hook once in `src/jev/core/` and register one `FeatureSpec`.
- Add a callable tool once in `src/jev/tooling.py` and register one `ToolSpec`; transports derive their exposure from the registry.
- Add a skill once under `.agents/skills/<name>/SKILL.md`. Every harness uses that canonical source.
- Change an adapter only for native protocol translation or a harness capability difference.
- Preserve the deterministic safety floor and harness-scoped audit identity.
- Keep project configuration unable to redirect trusted rule storage or weaken policy.

## Skills

Canonical custom skills live under [`.agents/skills/`](skills/). Antigravity may link that directory into its global configuration; Codex discovers the repository copy directly.

## Execution

The root [`AGENTS.md`](../AGENTS.md) and [`GEMINI.md`](../GEMINI.md) point here so every harness inherits the same instructions.

On Windows, prefix shell commands with `cmd /c` to ensure clean process termination and EOF delivery.

The default development install is user-scoped and editable. Keep exactly one Jev registration per device and harness. Codex loads matching hooks from both user and project configuration, so do not add a project Jev hook beside the user hook. Use a separate Codex home for isolated project-hook experiments.
