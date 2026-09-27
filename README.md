# Jev Shared Harness Runtime

[![System One](https://img.shields.io/badge/Architecture-System%20One%20Semantic%20Control-blue.svg)](https://docs.typesafe.ai)
[![Harnesses](https://img.shields.io/badge/Harnesses-Antigravity%20%7C%20Codex-orange.svg)](./proposals/RFC-24_CORE_shared_harness_runtime.md)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](./pyproject.toml)
[![Tests](https://img.shields.io/badge/Offline-passing-brightgreen.svg)](./tests/test_shared_runtime.py)

**One Jev implementation for Google Antigravity and OpenAI Codex.** Shared feature logic handles safety, skill routing, repository context, knowledge retrieval, semantic linting, persistence, and callable tools. Thin adapters translate each harness protocol.

---

## 1. Problem

Maintaining separate hook implementations causes policy drift. A safety fix may reach one harness first, duplicated skill routers may rank differently, and shared logs cannot identify their source.

## 2. Inspiration

Jev follows a ports-and-adapters design. Features consume one internal event contract. Harness adapters decode native input and encode native output while the core owns every decision.

## 3. Solution

The shared runtime provides:

- One typed feature registry for both harnesses.
- Deterministic safety invariants followed by optional Jev judgments.
- Canonical skills under `.agents/skills`.
- One SQLite database with `codex_events` and `antigravity_events` views.
- Configurable data, skill, knowledge, and cache roots.
- Optional MCP tools backed by the same core services.
- KI-style semantic lint rules with versioned SQLite decisions and feedback.

## 4. Concrete Example

`git reset --hard` reaches the same safety handler from either harness. The result is always `deny`; Antigravity receives its native decision JSON and Codex receives `permissionDecision: deny`. The audit record retains the originating harness.

## 5. Quick Start

Install the shared package and its MCP transport from the repository root:

```cmd
cmd /c python -m pip install --user -e ".[mcp]"
```

Set either provider key in your environment:

```cmd
cmd /c setx TYPESAFE_API_KEY "your-key"
```

Run diagnostics and offline tests:

```cmd
cmd /c python -m jev doctor --cwd .
cmd /c python -m pytest -q
```

Codex reads [`.codex/hooks.json`](.codex/hooks.json) and [`.codex/config.toml`](.codex/config.toml). Restart Codex after the editable install so `python -m jev` is available to its hook and MCP processes. See the [User Guide](docs/USER_GUIDE.md#12-new-machine-and-global-codex-setup) for user-wide setup.

For Antigravity, link the canonical hook directory and registration:

```cmd
cmd /c mklink /J "%USERPROFILE%\.gemini\config\hooks" "%CD%\.agents\hooks"
cmd /c mklink /J "%USERPROFILE%\.gemini\config\skills" "%CD%\.agents\skills"
cmd /c mklink "%USERPROFILE%\.gemini\config\hooks.json" "%CD%\.agents\hooks.json"
```

## 6. Architecture

```text
Antigravity JSON ─┐
                  ├─> adapter -> Event -> registry -> shared core -> Result -> adapter
Codex hook JSON ──┘                         │
                                           ├─ SQLite audit and rules
                                           └─ TypeSafe/OpenRouter client
```

| Component | Responsibility |
| --- | --- |
| [`contracts.py`](src/jev/contracts.py) | Harness-neutral events, operations, outcomes, and aggregation |
| [`registry.py`](src/jev/registry.py) | Single hook and tool extension surface |
| [`runtime.py`](src/jev/runtime.py) | Deadline-aware dispatch, decision replay, and logging |
| [`core/`](src/jev/core/) | Safety, skills, context prefetch, knowledge, and checkpoint logic |
| [`adapters/`](src/jev/adapters/) | Native Antigravity and Codex protocol translation |
| [`storage.py`](src/jev/services/storage.py) | Harness-tagged SQLite state and atomic invocation claims |
| [`semantic_lint.py`](src/jev/core/semantic_lint.py) | Bounded Git-diff evaluation against `.agents/lint-rules` |

## 7. Extending Jev

- Add a hook feature by writing one shared handler and adding one `FeatureSpec`.
- Add a callable tool by writing one handler and adding one `ToolSpec`; the MCP transport registers it automatically.
- Add a skill once under `.agents/skills/<name>/SKILL.md`.
- Add a semantic lint rule under `.agents/lint-rules/<rule-id>/`; start it in `observe` mode and promote it from reviewed evidence.

Adapters change only when a harness adds a new native lifecycle capability.

## 8. Documentation

- [User Guide](docs/USER_GUIDE.md)
- [Architecture Specification](docs/ARCHITECTURE.md)
- [RFC-24: Shared Harness Runtime](proposals/RFC-24_CORE_shared_harness_runtime.md)
- [RFC-08: Semantic Code Linting](proposals/RFC-08_USE_CASE_semantic_code_linting.md)
- [RFC Index](proposals/README.md)

## License

Jev is released under the MIT License and developed by [TypeSafe AI](https://docs.typesafe.ai).
