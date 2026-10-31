# RFC-27: OpenCode Harness Integration

> **Category**: CORE
> **Status**: Implemented; Windows live acceptance partial, Linux revalidation pending
> **Target Lifecycle**: `turn.before`, `tool.before`, `tool.after`, `context.checkpoint`
> **Harnesses**: OpenCode (third harness; Antigravity and Codex stay untouched)
> **Platforms**: Windows and Linux dual-boot — every gate runs on both boots, see §6
> **Implementation**: `src/jev/adapters/opencode.py`, `src/jev/install/opencode.py`, generated `plugins/jev.ts`
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
- **Startup self-test**: one `python -m jev doctor --cwd <directory>` probe and a worker readiness handshake. Failure reports degraded inspection and blocks gated calls. Read-only tools and workspace file edits remain available.
- **Pre-filter**: skip `read`, `glob`, `grep`, `list`, `lsp`, `skill`, `todowrite`, `question`, `webfetch`, `websearch` in JavaScript; only then spawn Python. Everything else (`bash`, `edit`, `write`, `apply_patch`, `task`, `jev_*` and other MCP tools) is inspected.
- **Transport**: one private `python -u -m jev hook-worker --harness opencode` process per plugin instance. UTF-8 JSON lines carry a request ID and payload; responses must match that ID and contain a valid decision. The bounded queue serializes requests. Deadlines include queue time: 1000ms for `tool.before`, 750ms elsewhere, with a separate 3000ms startup handshake. Timeout or crash closes the worker; the next request may restart it. Worker stderr stays separate from the protocol stream.
- **Fault policy**: transport failure blocks shell and other gated tools; file mutations and advisory hooks fail open. Read-only tools retain the native fast path. A returned `deny` or `ask` always throws.
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

#### Windows review — 2026-10-02

The Windows Python suite passes: **100 passed, 11 skipped**. Run from the repository root with `cmd /c uv run --no-project --with pytest pytest -q --basetemp=<fresh-temp-directory>`. Choose a fresh directory outside any checkout or ancestor containing `AGENTS.md`; workspace discovery otherwise correctly selects that ancestor. The checkout's `.venv` currently has no Windows Python executable.

The review fixed CRLF preservation during installer round trips and retained ownership records across reinstall, so uninstall still removes the keys originally added by Jev. OpenCode turn payloads now carry bounded prior context and the initial session objective into the shared Context Envelope. Three-harness integration tests cover safe-command allowance, destructive-command denial, and separate audit views. Codex and Antigravity adapter and core files remain unchanged.

Installed Windows OpenCode reports **1.18.32**. Its resolved global configuration has no Jev registration. The live Windows smoke matrix, plugin timing, MCP tool calls, and fresh Codex/Antigravity application sessions remain unverified. The Linux receipts below are historical evidence from 1.18.33; this Windows suite does not revalidate them. Compaction currently has a subscribed transport hook but no registered feature handling `CONTEXT_CHECKPOINT`, so an empty checkpoint response is expected.

#### Windows implementation follow-up — 2026-10-02

The follow-up supersedes the initial review above. The suite now passes **111 tests, with 11 skipped**. The worker, shared-runtime, and deadline checks also pass on the installed Python 3.10 interpreter (**28 passed**). Executable plugin checks run with `cmd /c npm exec --yes --package=tsx -- tsx tests/opencode_plugin_smoke.ts`; they exercise isolated instances, context recency, bounded state, session deletion, denial/approval outcomes, malformed responses, worker timeout/crash recovery, and failed startup probes. Python subprocess tests verify worker framing across all three harnesses and UTF-8 context handling on Windows.

OpenCode is installed globally using the existing Windows Python. The installer preserved the previous plugin, provider, permission, agent, and model values and retained its configuration backup. `opencode mcp list` reports Jev connected. Live sessions in a disposable workspace executed `echo JEV_WINDOWS_SAFE_OK`, edited a file, and called `jev_skills_list`, which returned seven canonical skills. `POST /session/:id/summarize` returned HTTP 200 and produced a `compaction` audit row. That first resumed session had no saved anchors; subsequent shared integration tests verify persistence, non-empty checkpoint delivery, harness/workspace/session isolation, and deletion.

Live validation exposed HTTP connection setup exceeding the socket timeout and intermittent failures from per-event process startup. The HTTP client now enforces elapsed-time limits; the plugin uses an instance-owned stdio worker. Three warm worker checks measured **300, 296, and 296 ms** after avoiding repeated schema initialization. This small sample does not establish P95 latency.

Shared runtime presentation now consumes adapter capabilities. Context anchors persist in the existing shared SQLite table; a registered compaction feature emits bounded source excerpts, and session cleanup removes them. Codex and Antigravity retain their presentation semantics, with regression coverage for both. Fresh Antigravity application acceptance, Linux revalidation of these changes, a larger latency sample, and native transcript replacement remain outstanding. The current Codex hook blocked the destructive-command test prompt before it reached OpenCode; executable plugin and Python integration tests cover denial without claiming a new native OpenCode destructive-command receipt.

#### Windows acceptance — 2026-10-02

Independent acceptance run against the installed Windows OpenCode **1.18.34** at `bca82bb`, driven by `docs/WINDOWS_OPENCODE_ACCEPTANCE.md`. Receipt: [`docs/testing/windows-opencode-acceptance.md`](../testing/windows-opencode-acceptance.md). Suite **111 passed, 11 skipped**, focused seven-file run **90 passed**, executable plugin smoke **passed**; `jev doctor` reports no problems, `opencode mcp list` reports `✓ jev connected`, and the config/plugin SHA-256 are byte-identical before and after — **no code or config change was required**. All eight S5 smoke items are checked off below; two optional receipts (`chat.message` mutation persisting, system-tail append rendering) stay `abstain` because no TypeSafe semantic client is configured on that boot, exactly as on Linux. One API delta for later: `POST /session/:id/summarize` now requires `{"providerID", "modelID"}` in the body on 1.18.34, and `POST /api/session/:id/compact` answers `503 Session compact is not available yet`.

- [x] `.gitattributes` with `* text=auto eol=lf` in place (landed at spec time; it collapsed the 30-file CRLF churn and emptied the phantom 228-line diff on `adapters/antigravity.py`).
- [ ] Run the suite on both boots; record both baselines side by side. **Linux: 36 passed, 11 skipped at S0 (2026-09-29); 96 passed, 11 skipped after S5 (2026-09-30) — the delta is this RFC's new tests. Windows: 111 passed, 11 skipped (2026-10-02, acceptance run — receipt below). Still open: Linux has not re-run the 2026-10-02 Windows follow-up changes, so the two numbers are not yet from one tree.**
- [x] Drop a temporary `~/.config/opencode/plugins/jev-spike.ts` (same directory on both OSes — verified, no Windows special case) that logs raw hook input and throws on a marked command. Spike source committed at `tests/fixtures/opencode/jev-spike.ts`; **must export `id`** (path plugins without `id` are rejected at load).
- [ ] Verify the five receipts on each boot's installed harness: throw blocks execution; `chat.message` mutation persists and reaches the model; system-tail append renders; `mcp.jev` discovers; plugin auto-load picks up the file. **Linux: all five ✓ (receipts below). Windows (2026-10-02): 3 of 5 ✓ — throw blocks execution, `mcp.jev` discovers (`opencode mcp list` → `✓ jev connected`), plugin auto-load picks up the file (`opencode debug config` → `file:///…/plugins/jev.ts` in `plugin_origins`). Not observed: `chat.message` mutation persisted byte-identical because every feature abstained (`semantic_unavailable`, no TypeSafe client on this boot), and the system-tail probe came back `NONE`. Receipt: `docs/testing/windows-opencode-acceptance.md`.**
- [x] Capture sanitized payloads into `tests/fixtures/opencode/{turn,tool_before,tool_after,checkpoint}.json`.
- [x] Record `opencode --version`, Python cold-start time, and end-to-end hook latency per boot. **Linux: recorded below. Windows (2026-10-02, n=10): `opencode --version` 1.18.34; interpreter cold start min 60.5 / p50 66.7 / p95 78.6 / max 78.6 ms; `python -m jev hook --harness opencode` safe `tool.execute.before` spawn round trip min 225.8 / p50 241.4 / p95 286.7 / max 286.7 ms (p95 inside the 300 ms budget); `python -m jev doctor` startup probe p50 934.3 ms of which `opencode --version` alone is p50 640.3 ms — inside the 3000 ms probe budget. Live footer latency 250.0–266.0 ms, dominated by the 250 ms semantic timeout. Full table in `docs/testing/windows-opencode-acceptance.md`.**

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

- [x] `contracts.py`: add `Harness.OPENCODE = "opencode"`.
- [x] `adapters/opencode.py`: decode/encode per §5.3–5.4; `adapters/__init__.py` export.
- [x] `cli.py`: add `opencode` to every `--harness` choice (`hook`, `authorize`, `stats`, `mcp`, `lint`).
- [x] `cli.py` malformed-input boundary: treat `hook: "tool.execute.*"` as pre-tool input, map `write`/`edit`/`apply_patch` onto the fail-open file-mutation set, and emit the `{"decision": …}` envelope instead of the Codex shape (finding F1 — without this, a malformed opencode shell payload fails open).
- [x] `runtime.py:67`: `inject_body = event.harness not in {Harness.CODEX, Harness.OPENCODE}`.
- [x] `services/storage.py`: `CREATE VIEW IF NOT EXISTS opencode_events …` beside the existing two.
- [x] `tests/test_opencode_adapter.py`: fixture round-trips, deny/ask/allow encoding, malformed shell fail-closed vs file fail-open, and `Harness.OPENCODE` accepted across every `--harness` CLI path. (Finding F2: `render.capability_manifest()` is feature-scoped and harness-neutral — the per-harness capability matrix stays docs-only, asserted at S5 in `docs/ARCHITECTURE.md`.)


**S1 gate result (Linux, 2026-09-29)**: suite 66 passed, 11 skipped — baseline 36 plus 30 new `test_opencode_adapter.py` cases (delta = this step's tests, skips unchanged); `git diff` over `adapters/{antigravity,codex}.py` and `core/` empty; no existing test file touched. One catch during implementation: merging `apply_patch` into the shared fail-open set changed Codex behavior (Codex ships its own `apply_patch` tool that must keep failing closed) — the boundary now keeps the Antigravity/Codex lines byte-identical behind a harness-scoped opencode branch, pinned by `test_codex_apply_patch_decode_error_still_fails_closed`. Windows run pending the Windows boot.

**Gate**: the suite reproduces the pre-change baseline on **both boots** (Linux: 36 passed, 11 skipped; Windows number from S0 — any delta needs an explanation, never a shrug), `git diff` over `src/jev/adapters/{antigravity,codex}.py` and `src/jev/core/` stays empty, and no Antigravity or Codex test file is edited. Shared files may receive additions only: a new enum member, new CLI choice strings, a new view, one extra condition in the `inject_body` expression, and the opencode branch of the `run_hook` malformed-input boundary. Any refactor of existing adapter logic stops the step.

### S2 — Registry-generated plugin (1 day)

- [x] `install/render.py`: `opencode_plugin()` (event subscriptions, pre-filter list, and timeouts derived from `FEATURES`) and `opencode_config()` (the `mcp.jev` fragment). The 270-line shim source lives in `install/templates.py` as `OPENCODE_JEV_TS`; `render.py` keeps the registry-derived surface (RFC §5.6 fixes those two entry points) and imports the blob. A non-Python template file would have been dropped by the wheel — `pyproject.toml` declares no package data.
- [x] Rendered `jev.ts` implements §5.5: `{ id: "jev", server() }` default export (S0: `id` is mandatory for path plugins), startup probe, pre-filter, spawn, fault policy, decision application, telemetry footer, and the §5.3 `agent` carry (`chat.message` reads `output.message`, the tool hooks read the session map).
- [x] Snapshot test asserting the rendered plugin tracks the registry (drift check, same idea as the other generated registrations).

**S2 gate result (Linux, 2026-09-29/30)**: `tests/test_opencode_render.py` — golden snapshot `tests/fixtures/opencode/jev.ts` byte-compared against `opencode_plugin()`, plus drift checks that recompute subscriptions from the *claimed* `FEATURES` triggers, recompute timeouts from `failure_policy == "secure"`, pin the ten-tool pre-filter, and assert the §5.3 envelope keys. Suite 73 passed, 11 skipped. `opencode debug config` reports `file:///…/plugins/jev.ts` in `plugin_origins` with no load errors; a direct import of the shim loads and runs `server()` in 63 ms.

**Gate**: rendered plugin loads in a live OpenCode window without publishing load errors. **✓ Linux.**

### S3 — Installer (1 day)

- [x] `src/jev/install/opencode.py`: config-dir resolution (§5.6, identical rule on both OSes), tolerant merge, ownership manifest, backup, refusal paths.
- [x] `jev install opencode [--global]` and `jev uninstall opencode` wired into `cli.py` (`--global` conflicts with `--dir`; `OPENCODE_CONFIG` is honored when neither flag is passed).
- [x] Tests under a temp `HOME`: preserves unrelated keys, refuses comment-bearing files, refuses an unmarked plugin file, uninstall restores byte-for-byte.
- [x] Path-rendering cases run on either OS: Windows-style inputs (`C:\Users\…`, backslash separators, `.exe` interpreter) exercised as pure string fixtures on Linux, and the real Windows path exercised on the Windows boot.

**S3 gate result (Linux, 2026-09-29)**: `tests/test_opencode_install.py` — 9 cases over a fake `HOME` (unrelated keys preserved, `provider`/`plugin`/`agent`/`permission`/`model` never rewritten, comment-bearing file refused before any write, foreign plugin refused with a merge instruction, round trip byte-identical, re-install idempotent, Windows path fixtures, `JEV_HOOK_PYTHON` accepted and rejected when relative). Suite 89 passed, 11 skipped. Live cycle on this machine: `jev install opencode` → `jev uninstall opencode` → `cmp` against the pre-install snapshot is byte-identical, shim and manifest gone, `opencode debug config` drops the origin; reinstalled for S4/S5. The plugin `plugin` array (magic-context) survived both cycles untouched.

**Gate**: install → restart OpenCode → uninstall → restart on **both boots**, with the user's existing `plugin` array intact through both cycles. **✓ Linux. Windows: pending the Windows boot.**

### S4 — Skills, tools, doctor (½ day)

- [x] Installer adds `skills.paths` (absolute path to `.agents/skills`) and `mcp.jev` (the `$schema` key is added only when missing; both are recorded in the ownership manifest so uninstall removes exactly these).
- [x] `install/doctor.py`: report config dir, plugin presence/ownership, skills path, `mcp.jev` state, interpreter, and `opencode --version`.
- [x] `cmd /c python -m jev doctor --cwd .` (Windows) / `.venv-linux/bin/python -m jev doctor --cwd .` (Linux) shows the opencode section.

**S4 gate result (Linux, 2026-09-29)**: `tests/test_opencode_doctor.py` — 7 cases (fresh install reports every registration, nothing installed reports no problem, missing `mcp.jev` / deleted shim / dropped `skills.paths` / unreadable config / broken interpreter each produce a problem). `jev doctor` prints the `opencode` section and exits `1` with one `missing OpenCode registration:` line per problem; sandboxed-XDG run reproduces `exit=1` when `mcp.jev` is removed and `exit=0` when intact.

**Gate**: `jev doctor` fails loudly when any registration is missing. **✓ Linux.**

### S5 — Docs and release gate (½ day)

- [x] Flip this RFC's status to `Implemented` (the proposals index row already exists as 📐 Blueprint).
- [x] `docs/ARCHITECTURE.md`: lifecycle table and capability matrix gain OpenCode columns.
- [x] `docs/USER_GUIDE.md`: OpenCode section — install, restart, `jev authorize` recovery flow, uninstall.
- [x] Root `README.md` stays ≤150 lines; harness badge and quickstart gain the third harness. `AGENTS.md` shared-runtime bullet gains the opencode registration line.
- [x] Live smoke matrix on **both boots**: startup context, turn context, harmless `bash` allowed, `rm -rf` denied, file edit allowed, MCP tool discovery, one skill visible to the `skill` tool, compaction hook fires (finding F3: an empty `checkpoint_context` is the expected payload until a feature claims `CONTEXT_CHECKPOINT` in `FEATURES` — assert the hook fires and accepts `output.context`, not a non-empty push). **Linux: all eight receipts below. Windows (2026-10-02, disposable workspace, OpenCode 1.18.34): all eight ✓ — startup probe `jev doctor` exits 0 with no plugin load error and telemetry footers on every tool output; turn context produced four `turn.before` rows, all `abstain` as on Linux, with anchors bounded (≤443 chars) and scoped by workspace/session; `echo JEV_WINDOWS_SAFE_OK` allowed with a `safety/tool.before` audit row; recursive delete denied as `Jev denied: Jev invariant blocked this operation (recursive_delete).` on `rmdir /s /q` — the cmd-shell equivalent of `rm -rf`, sentinel untouched; `hello.txt` written inside the workspace; `jev_skills_list` returned seven skills and the `skill` tool loaded `anti-slop-editor`; `POST /session/:id/summarize` → HTTP 200 with a `compaction` / `context.checkpoint` audit row carrying `{"anchor_count": 2}` and the prior messages left in place (no native replacement claimed). Receipt: `docs/testing/windows-opencode-acceptance.md`.**

#### S5 smoke matrix — Linux boot (2026-09-30)

Harness: `opencode serve` on port 4801, generated shim installed, free-tier `mimo-v2.6-flash-free`, DB at `~/.local/share/jev/jev.sqlite3` (`opencode_events`, 63 rows: 4 features × 13 `turn.before`, 7 `safety/tool.before`, 4 `knowledge_proposer/tool.after`).

| Item | Receipt |
| :--- | :--- |
| Startup context | No `session.start` in OpenCode (§5.1) — by design the shim runs `jev doctor --cwd <dir>` as its 3000 ms startup probe instead. |
| Turn context | `chat.message` fires for every message; `speculative`, `skills`, `knowledge`, `knowledge_proposer` each recorded 13 `turn.before` rows. All abstained — no TypeSafe client is configured on this boot, so no part was mutated (documented boundary: `semantic_unavailable` / `Outcome.Abstain`). |
| Harmless `bash` allowed | `echo jev-smoke-ok` → tool `completed`, and `tool.execute.after` appended the footer `<!-- jev-telemetry: 0 item(s) injected \| outcome: abstain \| latency: 140.4ms -->` to the tool output. |
| `rm -rf` denied | `rm -rf /tmp/jev-smoke/rm-target` → tool `error`, `Jev denied: Jev invariant blocked this operation (recursive_delete).` in 0.04 ms; target directory untouched. The shim throws (not `permissionDenied`) so OpenCode never falls back to its own permission path. |
| File edit allowed / ask flow | First `write /tmp/jev-smoke/hello.txt` (outside the workspace) → `needs_confirmation` / `sensitive_or_external_path` → encoded as `ask` → plugin threw `Jev requires explicit approval for this operation…` (the §4 recovery text, `permission.ask` being untriggerable). The model's retry into the workspace → `write /mnt/WORK/01_GIT/Jev/.jev-smoke.txt` → `workspace_file_fast_path` allow in 0.22 ms, tool `completed`. |
| MCP tool discovery | `mcp.jev` connected; `jev_semantic_lint` present in `/experimental/tool/ids`. Live calls: `jev_skills_list` → `completed`, `skill` tool → `completed`. |
| One skill visible to `skill` | `/skill` lists 18 entries from `.agents/skills`; the turn called `skill {"name": "anti-slop-editor"}` and completed. |
| Compaction hook fires | `POST /session/:id/summarize` → `true` in 6.1 s; an in-process `/proc` sampler observed `python -m jev hook --harness opencode` at **+0.040 s** (the only subscription active in that window), no plugin error in the OpenCode log, and `output.context` accepted with the empty payload F3 predicts. |

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
- Persistent worker implemented on 2026-10-02 as private stdio `jev hook-worker`; a standalone network service remains unnecessary.
- Native history replacement during compaction: disabled until OpenCode exposes a verified contract; `output.context` injection is the honest ceiling today.
