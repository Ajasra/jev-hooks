# RFC-27: OpenCode Harness Integration

> **Category**: CORE
> **Status**: 📐 Blueprint — Ready for Implementation
> **Target Lifecycle**: `turn.before`, `tool.before`, `tool.after`, `context.checkpoint`
> **Harnesses**: OpenCode (third harness; Antigravity and Codex stay untouched)
> **Platforms**: Windows and Linux dual-boot — every gate runs on both boots, see §6
> **Implementation**: planned — `src/jev/adapters/opencode.py`, `src/jev/install/opencode.py`, generated `plugins/jev.ts`
> **Related**: [RFC-24: Shared Harness Runtime](RFC-24_CORE_shared_harness_runtime.md) | [RFC-04: Safety Gate](RFC-04_CORE_safety_and_tool_guardrail.md) | [RFC-02: Dynamic Skill Dispatcher](RFC-02_CORE_dynamic_skill_dispatcher.md)

---

## 1. Problem

RFC-24 gave Jev one runtime behind two adapters, but both registrations still speak `hooks.json`. OpenCode does not read `hooks.json`. It loads JavaScript/TypeScript plugins, exposes a different lifecycle, and resolves its global configuration from `$XDG_CONFIG_HOME/opencode` — so today the only way to run Jev under OpenCode is to paste fragments into `~/.config/opencode/opencode.json` by hand.

Hand-pasted config has no ownership story. The live global file already carries a `plugin` array, a `provider` block, and its own `package.json`; a naive installer that rewrites it breaks the harness startup (OpenCode hard-fails on invalid config). Skills must appear in every project, not only inside this checkout. Tools must arrive through MCP. And the capability matrix must not promise an interactive approval modal the installed harness cannot render.

## 2. Inspiration

The same ports-and-adapters move that made RFC-24 work: feature logic consumes `Event` and returns `Result`, and a thin translator speaks the native dialect. Under OpenCode the dialect is a plugin — a small shim that receives hook input, hands it to `python -m jev hook --harness opencode`, and applies the returned decision.

The second lesson came from reading the installed binary instead of the manual. OpenCode 1.18.33 documents a `permission.ask` plugin hook; its source never triggers it. Designing the gate around a hook that does not fire would have shipped a safety gate that silently allows everything. Every binding in this RFC is tied to a trigger site verified at tag `v1.18.33`.

## 3. Solution

One Python adapter, one generated plugin, one idempotent installer.

- `adapters/opencode.py` decodes OpenCode hook JSON into portable events and encodes `Result` back into the plugin's decision envelope.
- `install/render.py` grows `opencode_plugin()` and `opencode_config()`, so registrations keep coming from the single feature registry.
- `jev install opencode` merges only Jev-owned keys into the global config, writes a marked `plugins/jev.ts`, and records an ownership manifest for a clean `jev uninstall opencode`.
- Skills ride the native discovery (`skills.paths`), tools ride `mcp.jev`, audit rows land in a new `opencode_events` view.

## 4. Concrete Example

Turn 1 in any repository: the user asks OpenCode to clean up build artifacts. `chat.message` fires, the shim spawns Jev, and the speculative arbiter plus knowledge engine return one text block that the plugin splices into the user message part — the model starts the turn knowing the dirty paths and the repo's packaging convention.

The model calls `bash` with `rm -rf build dist`. `tool.execute.before` fires before execution (`session/tools.ts:106`); Jev's deterministic shield classifies `recursive_delete` in under a millisecond and returns `deny`. The plugin throws, the tool part turns into an error carrying the reason, and no process is ever spawned. An ordinary `git status` on the next call takes the fast path: `allow`, no context, no visible friction.

## 5. Technical Specification

### 5.1 Evidence Base (verified against OpenCode `v1.18.33`)

| Fact | Source |
| :--- | :--- |
| Global config dir: `$XDG_CONFIG_HOME/opencode`, else `~/.config/opencode` | [`packages/core/src/global.ts`](https://github.com/anomalyco/opencode/blob/v1.18.33/packages/core/src/global.ts) |
| Plugins auto-load from `<config-dir>/{plugin,plugins}/*.{ts,js}` for every config directory | [`packages/opencode/src/config/plugin.ts:19-30`](https://github.com/anomalyco/opencode/blob/v1.18.33/packages/opencode/src/config/plugin.ts), invoked at [`config/config.ts:478`](https://github.com/anomalyco/opencode/blob/v1.18.33/packages/opencode/src/config/config.ts) |
| `tool.execute.before` runs before the tool body; thrown errors propagate as tool failures | [`session/tools.ts:106-111`](https://github.com/anomalyco/opencode/blob/v1.18.33/packages/opencode/src/session/tools.ts) |
| `chat.message` fires while the user message is created; mutations persist with it | [`session/prompt.ts:1000`](https://github.com/anomalyco/opencode/blob/v1.18.33/packages/opencode/src/session/prompt.ts) |
| `experimental.chat.system.transform` runs per LLM request (plus title/summary path) | [`session/llm/request.ts:70`](https://github.com/anomalyco/opencode/blob/v1.18.33/packages/opencode/src/session/llm/request.ts), [`agent/agent.ts:381`](https://github.com/anomalyco/opencode/blob/v1.18.33/packages/opencode/src/agent/agent.ts) |
| `experimental.session.compacting` accepts `output.context` / `output.prompt` | [`session/compaction.ts`](https://github.com/anomalyco/opencode/blob/v1.18.33/packages/opencode/src/session/compaction.ts) |
| Skill scan roots: `~/.agents/skills`, `~/.claude/skills`, config dirs, `skills.paths`, upward `.agents` scan | [`skill/index.ts:180-216`](https://github.com/anomalyco/opencode/blob/v1.18.33/packages/opencode/src/skill/index.ts) |
| MCP tool ids are `<server>_<tool>`; built-ins are `bash`, `edit`, `write`, `apply_patch`, `task`, `read`, `glob`, `grep`, `skill` | [`mcp/catalog.ts:119`](https://github.com/anomalyco/opencode/blob/v1.18.33/packages/opencode/src/mcp/catalog.ts), [`tool/shell/id.ts:16`](https://github.com/anomalyco/opencode/blob/v1.18.33/packages/opencode/src/tool/shell/id.ts) |
| `permission.ask` is declared but never triggered by this release | no `trigger("permission.ask")` anywhere in the tag; the string appears only inside embedded docs |

### 5.2 Lifecycle Mapping

| Portable event | OpenCode hook | Effect | Capability |
| :--- | :--- | :--- | :--- |
| `turn.before` | `chat.message` | Splice Jev context into the user message's text part; once per message, persists as history | `verified` (S0 receipt) |
| `tool.before` | `tool.execute.before` | `deny`/`ask` → throw (execution blocked, reason reaches the model); advisory items → per-session queue | `verified` (S0 receipt) |
| `tool.after` | `tool.execute.after` | Append bounded `<!-- jev-telemetry -->` footer to the tool output | `verified` (S0 receipt) |
| advisory drain + session knowledge | `experimental.chat.system.transform` | Append stable text at the tail of `system[]` (idempotent, cache-safe) | `verified` (S0 receipt) |
| `context.checkpoint` | `experimental.session.compacting` | Push strings into `output.context`; sidecar checkpoint only | `unverified` (S5 smoke) |
| `session.start` / `session.end` | `event` (`session.created`, `session.deleted`, `session.idle`) | Fire-and-forget: knowledge seed, audit flush | `unsupported` for context injection — no output channel |

Tool → `Operation` translation: `bash` → `shell` (`args.command`), `write`/`edit`/`apply_patch` → `file_mutation` (`args.filePath`, `args.patchText`), `task` and MCP tools → `tool`. Shell dialect is taken from `args.shell` when present.

### 5.3 Payload Contract (plugin → `python -m jev hook --harness opencode`, stdin)

```json
{
  "hook": "tool.execute.before",
  "harness_version": "1.18.33",
  "cwd": "/abs/project",
  "session_id": "ses_…",
  "turn_id": "msg_…",
  "agent": "build",
  "prompt": "clean up the build artifacts",
  "tool": {"name": "bash", "call_id": "call_…", "args": {"command": "rm -rf build"}},
  "native": {"…": "raw hook input for diagnostics"}
}
```

`prompt` is the joined text of the message parts (`chat.message`), empty for tool hooks. `tool` is absent on turn hooks; `result` (tool output, title, metadata) is added on `tool.execute.after`. Decoding follows the existing adapter rules: unknown fields stay in `native`, missing identity stays empty, and malformed tool input fails closed for shell and open for file mutations — the boundary already encoded in `cli.run_hook`, whose trigger detection keys on `hook_event_name`/`hookEventName`/`toolCall` today and therefore gains the opencode `hook` field plus the `write`/`edit`/`apply_patch` fail-open names at S1.

### 5.4 Output Contract (stdout → plugin)

```json
{"decision": "allow|deny|ask", "reason": "…", "reason_code": "…",
 "context": "…", "footer": "…", "checkpoint_context": ["…"]}
```

- `deny` → the plugin throws; the tool never executes.
- `ask` (Jev `needs_confirmation`) → the plugin throws with user-facing text stating that explicit approval is required. The approval command itself stays out of model-visible output — RFC-24 forbids telling the agent to run the grant command — and is printed by `jev authorize` on stderr plus documented in `docs/USER_GUIDE.md`.
- `context` → appended to the user message's text part (turn hooks) or queued to the system tail (tool hooks).
- `footer` → appended to the tool output.
- `checkpoint_context` → pushed into `output.context`.

JSON goes to stdout only; diagnostics go to stderr, same as every existing hook.

### 5.5 Generated Plugin (`~/.config/opencode/plugins/jev.ts`)

- **Identity**: default export `{ id: "jev", server() { … } }` — OpenCode rejects path plugins that do not export `id` (S0 receipt), and only the `server()` side matters: `tool.execute.before`/`after` fire in the server process, not the TUI.
- **Startup self-test**: one `python -m jev doctor --cwd <directory>` probe. On failure the plugin publishes a single session error, disables gating for the process, and keeps OpenCode usable — an unsupported capability gets reported, never silently claimed. Native OpenCode permissions remain the floor either way.
- **Pre-filter**: skip `read`, `glob`, `grep`, `list`, `lsp`, `skill`, `todowrite`, `question`, `webfetch`, `websearch` in JavaScript; only then spawn Python. Everything else (`bash`, `edit`, `write`, `apply_patch`, `task`, `jev_*` and other MCP tools) is inspected.
- **Spawn**: stdin JSON, stdout JSON, hard timeout 1000ms for `tool.before` and 750ms elsewhere; stderr passes through to the harness log.
- **Fault policy**: spawn failure, timeout, or unparsable stdout → continue (fail-open) plus one bounded session error per session. A `deny` or `ask` that did arrive always throws — an established denial is never dropped on the floor.
- **Load safety**: the module never throws during import; every hook body is wrapped. A broken Jev shim must degrade to a missing gate while the session keeps running.
- **Telemetry**: identical footer shape to the Antigravity and Codex adapters.

### 5.6 Global Installer (`jev install opencode` / `jev uninstall opencode`)

Config directory resolution mirrors OpenCode itself, verified against `xdg-basedir@5.1.0`, which has no `win32` branch: the global config lives at `$(XDG_CONFIG_HOME || ~/.config)/opencode/opencode.json` on both boots — on Windows that is `%USERPROFILE%\.config\opencode`, the same rule, never `%APPDATA%`. When `OPENCODE_CONFIG` points at a file, that file is the target instead; `OPENCODE_CONFIG_DIR` adds a *second* search directory rather than replacing the global one, so the installer writes the global file unless `--dir` names another. The `skills.paths` entry is emitted as an absolute path of the checkout — JSON escaping covers Windows backslashes, and OpenCode's path handling accepts either separator.

Merge rules:

- Parse `opencode.json` (or `opencode.jsonc`, or create `opencode.json` when neither exists). A file that fails to parse aborts the install untouched — comments, unknown keys, and every unrelated field survive byte-for-byte.
- Add only owned keys: the `skills.paths` entry pointing at this checkout's `.agents/skills`, the `mcp.jev` server block, and `$schema` when missing. Never write `plugin`, `provider`, `agent`, `permission`, or `model`.
- Write `plugins/jev.ts` only when absent or when it carries the `// @jev-owned` header. A user-edited file without the header refuses the overwrite and prints the merge instruction.
- Persist `.jev-install.json` (owned keys, plugin path, backup path) so uninstall removes exactly what install added and nothing else.
- Timestamped backup of every file before the first write.

The MCP block rendered from the registry:

```json
"mcp": {"jev": {"type": "local",
  "command": ["<resolved-python>", "-m", "jev", "mcp", "--cwd", ".", "--harness", "opencode"],
  "enabled": true}}
```

The interpreter is resolved at install time (the same one used for `pip install`) and rendered as an absolute path per boot — `…\.venv\Scripts\python.exe` on Windows, `…/.venv-linux/bin/python` on Linux — overridable later through `JEV_HOOK_PYTHON`. No reliance on `PATH` inside the harness process, and no assumption that one boot's absolute path exists on the other.

### 5.7 Capability Manifest

| Capability | OpenCode binding | Status |
| :--- | :--- | :--- |
| Safety gate (hard deny) | `tool.execute.before` → throw | `verified` after S0 receipt |
| Interactive confirmation | — | `unsupported` → deny plus `jev authorize` one-use CLI |
| Speculative prefetch | `chat.message` splice | `verified` after S0 receipt |
| Dynamic skill routing | hint-only (`inject_body=False`); OpenCode's native `skill` tool loads bodies | `verified` |
| Knowledge engine | `chat.message` + stable system-tail text | `verified` after S0 receipt |
| Output verification | `tool.execute.after` footer + system-tail queue | `verified` after S0 receipt |
| Semantic lint / callable tools | `mcp.jev` from the registry | `unverified` until S5 smoke |
| Context compactor | `experimental.session.compacting` (`output.context` only) | `unverified` until S5 smoke |
| Audit persistence | `opencode_events` view | `verified` |

### 5.8 Latency and Trust Boundaries

Jev's budgets do not move: 0.30s dispatch deadline, 0.25s semantic timeout. Added wall time is dominated by the Python cold start; S0 measures it, and the P95 target stays ≤300ms total per RFC-24 §5.8. If the measurement misses, the fix is a persistent `jev serve` worker (deferred, §10) — the deadlines themselves stay fixed.

Jev returns `allow` — never a bypass. OpenCode's own permission rules, sandbox, and approval flow stay authoritative exactly as they do for the other two harnesses. Project-level `.opencode/` config can add skills and plugins; it cannot disable the global shim or rewrite the owned `mcp.jev` block. Event rows keep `harness = 'opencode'` so shared storage stays harness-scoped.

## 6. Implementation Sequence

Each step ends green on **both boots** before the next begins. The two boots share one checkout, so every gate runs twice:

| Boot | Suite command | Notes |
| :--- | :--- | :--- |
| Windows | `cmd /c .venv\Scripts\python -m pytest -q` | the existing `.venv` from the primary install |
| Linux | `.venv-linux/bin/python -m pytest -q` | `.venv-linux` created at S0: `uv venv .venv-linux` + `uv pip install --python .venv-linux/bin/python -e ".[test,mcp]"` (`mcp` added by the S0 R4 receipt — the MCP server refuses to start without it) |

The Linux baseline is already recorded: 36 passed, 11 skipped. S0 records the Windows number beside it — identical counts are the expectation, because the suite is pathlib-clean. Fixtures and tests must stay OS-agnostic: no separator assumptions, no drive-letter or home-directory literals.

### S0 — Contract spike (½ day)

- [x] `.gitattributes` with `* text=auto eol=lf` in place (landed at spec time; it collapsed the 30-file CRLF churn and emptied the phantom 228-line diff on `adapters/antigravity.py`).
- [ ] Run the suite on both boots; record both baselines side by side. **Linux: 36 passed, 11 skipped (2026-09-29, reproduced again after fixtures landed). Windows: pending the Windows boot.**
- [x] Drop a temporary `~/.config/opencode/plugins/jev-spike.ts` (same directory on both OSes — verified, no Windows special case) that logs raw hook input and throws on a marked command. Spike source committed at `tests/fixtures/opencode/jev-spike.ts`; **must export `id`** (path plugins without `id` are rejected at load).
- [ ] Verify the five receipts on each boot's installed harness: throw blocks execution; `chat.message` mutation persists and reaches the model; system-tail append renders; `mcp.jev` discovers; plugin auto-load picks up the file. **Linux: all five ✓ (receipts below). Windows: pending.**
- [x] Capture sanitized payloads into `tests/fixtures/opencode/{turn,tool_before,tool_after,checkpoint}.json`.
- [ ] Record `opencode --version`, Python cold-start time, and end-to-end hook latency per boot. **Linux: recorded below. Windows: pending.**

**Gate**: every receipt written down; payload fixtures committed; if any binding fails, revise §5.2 before touching `src/`. **No binding failed on the Linux boot — §5.2 stands as written.**

#### S0 receipts — Linux boot (2026-09-29)

| Item | Result |
| :--- | :--- |
| `opencode --version` | `1.18.33` (exact evidence tag of §5.1) |
| Suite baseline | 36 passed, 11 skipped (re-run after fixtures: identical) |
| R1 throw blocks execution | `echo JEV_SPIKE_DENY` → tool failed with `jev-spike: blocked marked command`; model reported "command was intercepted and did not run" — no process spawned |
| R2 `chat.message` persists + reaches model | model replied `SPIKE_TURN_OK` to the injected marker; `opencode export` shows `<jev-spike>SPIKE_TURN_MARKER</jev-spike>` persisted in the stored user text part |
| R3 system-tail renders | model listed `SPIKE_SYSTEM_INSTRUCTION_OK` injected via `experimental.chat.system.transform` |
| R4 `mcp.jev` discovers | `opencode mcp list` → `✓ jev connected` with the rendered command; required the `mcp` extra in `.venv-linux` (`uv pip install -e ".[test,mcp]"`). S0 rendered `--harness codex` as a stand-in — the `opencode` choice lands at S1 |
| R5 plugin auto-load | `opencode debug config` shows `plugins/jev-spike.ts` auto-discovered into the resolved `plugin` array while the on-disk `opencode.json` stays untouched; `loaded.txt` marker written at boot |
| Checkpoint capture | `POST /session/:id/summarize` drove `experimental.session.compacting` with `{sessionID}` → `{context: []}`; this is the S5 smoke recipe |
| Python cold start (external, n=10) | min 66 ms / p50 67 ms / p95 67 ms / max 67 ms (`python -m jev doctor`) |
| End-to-end hook latency in-harness (n=4) | 66–73 ms from `tool.execute.before` entry through spawn+doctor round trip — ~4× headroom under the 300 ms budget |
| Environment notes | path plugins need `id`; `chat.message` input carries only `sessionID` (agent/model/`messageID` live on `output.message`); `tool.execute.before` args arrive in `output.args`, `tool.execute.after` args in `input.args`; the title-agent free-tier stream error (`agent=title`) is a CLI-only artifact and does not affect build-agent calls; live config is strict JSON with no comments, so the S3 parse-or-abort rule holds on this machine |

### S1 — Contracts and adapter (1 day)

- [ ] `contracts.py`: add `Harness.OPENCODE = "opencode"`.
- [ ] `adapters/opencode.py`: decode/encode per §5.3–5.4; `adapters/__init__.py` export.
- [ ] `cli.py`: add `opencode` to every `--harness` choice (`hook`, `authorize`, `stats`, `mcp`, `lint`).
- [ ] `cli.py` malformed-input boundary: treat `hook: "tool.execute.*"` as pre-tool input, map `write`/`edit`/`apply_patch` onto the fail-open file-mutation set, and emit the `{"decision": …}` envelope instead of the Codex shape (finding F1 — without this, a malformed opencode shell payload fails open).
- [ ] `runtime.py:67`: `inject_body = event.harness not in {Harness.CODEX, Harness.OPENCODE}`.
- [ ] `services/storage.py`: `CREATE VIEW IF NOT EXISTS opencode_events …` beside the existing two.
- [ ] `tests/test_opencode_adapter.py`: fixture round-trips, deny/ask/allow encoding, malformed shell fail-closed vs file fail-open, and `Harness.OPENCODE` accepted across every `--harness` CLI path. (Finding F2: `render.capability_manifest()` is feature-scoped and harness-neutral — the per-harness capability matrix stays docs-only, asserted at S5 in `docs/ARCHITECTURE.md`.)

**Gate**: the suite reproduces the pre-change baseline on **both boots** (Linux: 36 passed, 11 skipped; Windows number from S0 — any delta needs an explanation, never a shrug), `git diff` over `src/jev/adapters/{antigravity,codex}.py` and `src/jev/core/` stays empty, and no Antigravity or Codex test file is edited. Shared files may receive additions only: a new enum member, new CLI choice strings, a new view, one extra condition in the `inject_body` expression, and the opencode branch of the `run_hook` malformed-input boundary. Any refactor of existing adapter logic stops the step.

### S2 — Registry-generated plugin (1 day)

- [ ] `install/render.py`: `opencode_plugin()` (event subscriptions, pre-filter list, and timeouts derived from `FEATURES`) and `opencode_config()` (the `mcp.jev` fragment).
- [ ] Rendered `jev.ts` implements §5.5: `{ id: "jev", server() }` default export (S0: `id` is mandatory for path plugins), startup probe, pre-filter, spawn, fault policy, decision application, telemetry footer.
- [ ] Snapshot test asserting the rendered plugin tracks the registry (drift check, same idea as the other generated registrations).

**Gate**: rendered plugin loads in a live OpenCode window without publishing load errors.

### S3 — Installer (1 day)

- [ ] `src/jev/install/opencode.py`: config-dir resolution (§5.6, identical rule on both OSes), tolerant merge, ownership manifest, backup, refusal paths.
- [ ] `jev install opencode [--global]` and `jev uninstall opencode` wired into `cli.py`.
- [ ] Tests under a temp `HOME`: preserves unrelated keys, refuses comment-bearing files, refuses an unmarked plugin file, uninstall restores byte-for-byte.
- [ ] Path-rendering cases run on either OS: Windows-style inputs (`C:\Users\…`, backslash separators, `.exe` interpreter) exercised as pure string fixtures on Linux, and the real Windows path exercised on the Windows boot.

**Gate**: install → restart OpenCode → uninstall → restart on **both boots**, with the user's existing `plugin` array intact through both cycles.

### S4 — Skills, tools, doctor (½ day)

- [ ] Installer adds `skills.paths` (absolute path to `.agents/skills`) and `mcp.jev`.
- [ ] `install/doctor.py`: report config dir, plugin presence/ownership, skills path, `mcp.jev` state, interpreter, and `opencode --version`.
- [ ] `cmd /c python -m jev doctor --cwd .` (Windows) / `.venv-linux/bin/python -m jev doctor --cwd .` (Linux) shows the opencode section.

**Gate**: `jev doctor` fails loudly when any registration is missing.

### S5 — Docs and release gate (½ day)

- [ ] Flip this RFC's status to `Implemented` (the proposals index row already exists as 📐 Blueprint).
- [ ] `docs/ARCHITECTURE.md`: lifecycle table and capability matrix gain OpenCode columns.
- [ ] `docs/USER_GUIDE.md`: OpenCode section — install, restart, `jev authorize` recovery flow, uninstall.
- [ ] Root `README.md` stays ≤150 lines; harness badge and quickstart gain the third harness. `AGENTS.md` shared-runtime bullet gains the opencode registration line.
- [ ] Live smoke matrix on **both boots**: startup context, turn context, harmless `bash` allowed, `rm -rf` denied, file edit allowed, MCP tool discovery, one skill visible to the `skill` tool, compaction hook fires (finding F3: an empty `checkpoint_context` is the expected payload until a feature claims `CONTEXT_CHECKPOINT` in `FEATURES` — assert the hook fires and accepts `output.context`, not a non-empty push).

**Gate**: full suite green on both boots, smoke matrix receipts recorded per boot, capability table matches observed behavior.

## 7. Validation and Release Gates

- Non-interference first: record both boots' suite baselines before S1 (Linux: 36 passed, 11 skipped; Windows recorded at S0) and reproduce them after every step. Measured against the tree as S1 found it, `git diff --stat` over `src/jev/adapters/antigravity.py`, `src/jev/adapters/codex.py`, and `src/jev/core/` must stay empty for the whole sequence — those files carry Antigravity and Codex behavior, and the opencode work has no business inside them.
- Replay both fixture families (Antigravity, Codex, OpenCode) through decode → core → encode and compare semantic outcomes across harness dialects.
- Install/uninstall round-trip must be byte-identical for every key Jev does not own.
- Generated plugin output must drift-test against the registry.
- Malformed and hostile payloads: wrong `hook` name, missing `args`, truncated stdout, non-JSON stdout, timeout, and a project `.opencode/` config trying to weaken the gate.
- Deterministic checks stay offline; live provider calls only in the opt-in smoke suite.
- Established denials survive replay: redelivering the same `call_id` with a stored deny must deny again.

## 8. Rollback and Risks

Uninstall removes owned config keys, the marked plugin file, and nothing else; the SQLite side needs no migration (one additive view). Knowledge items and rules stay put.

| Risk | Handling |
| :--- | :--- |
| `chat.message` part schema rejects an injected part | Mutate an existing text part only; when none exists, fall back to the system-tail queue instead of appending a new part |
| System-tail churn breaks prompt caching | Identical text per session, appended at the tail; queue drains once |
| Python spawn misses the budget | Measure in S0; persistent worker is §10, deadlines do not move |
| Comment-bearing `opencode.json` | Abort untouched with the parse error; never rewrite user config blindly |
| Upstream ships `permission.ask` for real | Revisit §5.4: `ask` maps to `status:"ask"` and the manual CLI becomes a fallback |
| Shim or interpreter breaks mid-session | Fail-open after the startup probe's warning, one bounded session error, native permissions still apply |
| Dual-boot line-ending churn fakes regressions | `.gitattributes` pins `* text=auto eol=lf` (landed at spec time); `git diff` guards measure content on either boot |

## 9. Decisions and Evidence

Why a plugin shim: MCP exposes callable tools but cannot sit in front of `bash`, so the gate needs a hook, and plugins are OpenCode's only hook surface. Why `chat.message`: the alternative `experimental.chat.messages.transform` re-runs on every LLM request, which duplicates injection and churnes the prompt cache, while `chat.message` fires once per user message. Why throw-to-block: `permission.ask` never fires in 1.18.33 (§5.1), and a server-plugin ↔ TUI-plugin handshake would blow the 0.30s deadline.

Repository evidence: [shared runtime](../../src/jev/runtime.py), [registry](../../src/jev/registry.py), [renderers](../../src/jev/install/render.py), [hook boundary](../../src/jev/cli.py), [Codex registration](../../.codex/hooks.json). OpenCode sources checked against tag `v1.18.33` of `anomalyco/opencode` on 2026-09-29; §5.1 links each claim to its file. S0 re-verifies every binding on the live binary before implementation proceeds.

## 10. Deferred

- Interactive confirmation modal: needs upstream to trigger `permission.ask`, or a cross-process TUI handshake; its roundtrip likely exceeds the dispatch deadline, so it earns its own RFC.
- Persistent `jev serve` worker to remove per-event Python cold start.
- Native history replacement during compaction: disabled until OpenCode exposes a verified contract; `output.context` injection is the honest ceiling today.
