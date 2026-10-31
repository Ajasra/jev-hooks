# Windows OpenCode Acceptance Receipt

> **Date**: 2026-10-02
> **Contract**: [RFC-27](../proposals/RFC-27_CORE_opencode_harness.md)
> **Scope**: Windows live acceptance for the OpenCode harness only. Antigravity and Codex were not touched.
> **Outcome**: all offline checks green; 8 of 8 required live checks pass; 2 optional receipts observed as `abstain`; no code or config change was needed.

## 1. Environment

| Item | Value |
| :--- | :--- |
| OS | Windows (win32), user profile `%USERPROFILE%` |
| Python | 3.10.9 — `%LOCALAPPDATA%\Programs\Python\Python310\python.exe` |
| OpenCode | `1.18.34` at start **and** at end (RFC-27 previously recorded `1.18.32`; the binary has moved) |
| Jev revision | `bca82bb245389dc3ccdcef516878f33b11b71d47` (`feat(opencode): add RFC-27 S2-S5 plugin, installer, doctor, and docs`) |
| Working tree at start | 25 modified + 8 untracked entries — pre-existing in-progress user changes, preserved throughout |
| Jev data root | `%LOCALAPPDATA%\Jev` (`jev.sqlite3`) |
| Git | checkout owned by `BUILTIN/Administrators`; every git call used `git -c safe.directory=D:/01_GIT/Jev …` per invocation so the user's global git config was never modified |

## 2. Starting install state

`cmd /c python -m jev doctor --cwd .` — `installed: true`, `plugin_state: owned`, `mcp.present: true`, `mcp.enabled: true`, `mcp.matches_interpreter: true`, `skills_paths: [D:\01_GIT\Jev\.agents\skills]`, `problems: []`.

Sanitized snapshot of the files an install/uninstall round trip would touch (hashes only):

| File | Bytes | SHA-256 (start) | SHA-256 (end) |
| :--- | ---: | :--- | :--- |
| `%USERPROFILE%\.config\opencode\opencode.jsonc` | 964 | `3440fa88…53c781d6` | `3440fa88…53c781d6` (unchanged) |
| `%USERPROFILE%\.config\opencode\plugins\jev.ts` | 15933 | `ddec49db…72af6dd` | `ddec49db…72af6dd` (unchanged) |
| `%USERPROFILE%\.config\opencode\.jev-install.json` | 1033 | `6b92150f…e7aff9ff7` | (read-only; not rewritten) |

Ownership manifest: `owned_keys: ["mcp.jev", "skills.paths"]`, `created_containers: ["skills", "skills.paths"]`, `config_existed: true`, backup `opencode.jsonc.jev-20261002-113721.bak` retained.

Config shape observed (values redacted, no secrets):

- top-level keys: `$schema`, `compaction`, `mcp`, `plugin`, `skills`
- `plugin`: `["@cortexkit/opencode-magic-context@latest"]` — user-owned, never rewritten
- `mcp`: `jev` (Jev-owned) plus unrelated `notion-opencalls` and `td` — both preserved
- no `provider` / `permission` / `agent` / `model` keys exist in this file, so none could be touched
- `comment_free: false` — the file carries JSONC comments; the installer's parse-or-abort rule is therefore live on this machine

## 3. Offline checks

### 3.1 Baseline problem with the task's literal command (environment, not Jev)

Running the task's command verbatim fails before any test executes:

```
cmd /c python -m pytest -q tests/…
→ PermissionError: [WinError 5] Access is denied:
  'C:\Users\<user>\AppData\Local\Temp\pytest-of-user'
→ 37 passed, 53 errors
```

`%TEMP%\pytest-of-user` is ACL-denied for this account, so pytest cannot create its basetemp. This is a machine-level permission problem, not a Jev defect: no test body ran. Re-running with a fresh `--basetemp` outside the checkout (the recipe RFC-27 §S0 already documents for Windows) is green.

### 3.2 Focused run

```cmd
cmd /c python -m pytest -q --basetemp="%TEMP%\opencode\jev-acc-basetemp-20261002" tests\test_opencode_adapter.py tests\test_opencode_render.py tests\test_opencode_install.py tests\test_opencode_doctor.py tests\test_shared_runtime.py tests\test_hook_worker.py tests\test_client_deadline.py
```

**90 passed, 0 skipped, 0 failed** (23.42 s). All seven named files exist in this checkout.

### 3.3 Full suite

```cmd
cmd /c python -m pytest -q --basetemp="%TEMP%\opencode\jev-acc-basetemp-full-20261002"
```

**111 passed, 11 skipped, 0 failed** (29.63 s) — reproduces the count RFC-27's Windows implementation follow-up records, and the skip set is unchanged.

### 3.4 Executable plugin smoke

```cmd
cmd /c npm exec --yes --package=tsx -- tsx tests\opencode_plugin_smoke.ts
```

**passed** — `OpenCode plugin smoke passed: instance isolation, recency, errors, cleanup, bounded state, denial and fault policy`.

The two alarming lines above it are *expected output of the deliberate broken-instance scenario*:

- `[jev] self-test failed: jev doctor exited with status 1`
- `[jev] tool.execute.before inspection unavailable`

asserted by `await assert.rejects(() => tool(broken), /self-test failed/)` at `tests/opencode_plugin_smoke.ts:87`. `git status --short` after the run shows no new lockfile or project-config entry, so `npm exec` stayed ephemeral.

## 4. Install and doctor behaviour

Jev was **already installed and healthy** at start, so per the task rules **no install or uninstall was executed** — no round trip was performed, because none was required and performing one would only risk the user's working integration.

| Command | Result |
| :--- | :--- |
| `cmd /c python -m jev doctor --cwd .` | `problems: []` at start **and** end; reports config dir `%USERPROFILE%\.config\opencode`, config file `opencode.jsonc`, `plugin_state: owned`, `skills_paths`, `mcp.jev` present+enabled, interpreter `%LOCALAPPDATA%\Programs\Python\Python310\python.exe`, `opencode_version: 1.18.34` |
| `cmd /c opencode mcp list` | `✓ jev connected` at start **and** end (`python.exe -m jev mcp --cwd . --harness opencode`) |
| `cmd /c opencode debug config` (cwd = disposable workspace) | `plugin_origins` contains `file:///C:/Users/<user>/.config/opencode/plugins/jev.ts` (global scope) **and** the user's `@cortexkit/opencode-magic-context@latest`; `mcp` still holds `notion-opencalls`, `td`, `jev`; `skills.paths` points at this checkout. No load error reported. |
| config / plugin SHA-256 | byte-identical before and after every check |

## 5. Live checks — disposable workspace

Workspace: `%TEMP%\opencode\jev-win-acc-20261002-125445-fona` (created fresh, unique suffix `-fona`; sentinel at `…\denial-20261002-125445-fona\SENTINEL.txt`). Sessions started with `opencode run --auto --dir <workspace>` and with `opencode serve --port 4899` + HTTP. The directory was confirmed by resolved path and removed only after all checks finished.

Audit DB: `%LOCALAPPDATA%\Jev\jev.sqlite3`, view `opencode_events`. Before live checks: 72 rows, `deny: 1`. After: 250 rows, `abstain: 134, allow: 113, deny: 3` — every new row carries `harness = 'opencode'`.

| # | Check | Result | Receipt |
| :-: | :--- | :-: | :--- |
| 1 | Startup/doctor probe completes, generated plugin loads without errors | **pass** | `plugin_origins` lists `plugins/jev.ts`; `opencode serve` stdout/stderr contain no `[jev]` load error; every tool output in the session carries `<!-- jev-telemetry: … -->`, which only the live shim emits; `jev doctor` exits 0 |
| 2 | A user turn reaches Jev context handling; recent objective/error context bounded and does not leak across sessions | **pass** | `ses_f04eb835…` produced four `turn.before` rows (`speculative`, `skills`, `knowledge`, `knowledge_proposer`). `session_context` rows are scoped by `workspace_id` (`57e86eea…` for the disposable workspace vs `89774075…` for the Jev checkout) and by `session_id`; anchor sizes across all opencode sessions max out at 400 (`session_objective`) / 443 (`prior_context`) characters; no row from another session or workspace appears in the disposable sessions |
| 3 | Harmless command `echo JEV_WINDOWS_SAFE_OK` allowed and leaves a safety audit event | **pass** | tool completed, output `JEV_WINDOWS_SAFE_OK`; `safety / tool.before / allow` rows recorded (e.g. `reason_code: semantic_unavailable`); footer `latency: 250.0ms` appended to the tool output |
| 4 | Write/edit inside the disposable workspace succeeds | **pass** | `hello.txt` written, content `JEV_WINDOWS_WRITE_OK`, read back from disk |
| 5 | Jev MCP tools discoverable; `jev_skills_list` runs; OpenCode `skill` tool sees and loads a canonical Jev skill | **pass** | `jev_skills_list` → **7 skills** (`anti-slop-editor`, `context-architect`, `doc-architect`, `lint-architect`, `skill-architect`, `system-one-balance-protocol`, `typesafe-ai`); `skill {"name":"anti-slop-editor"}` loaded, first heading `# Skill: anti-slop-editor` |
| 6 | Summarize/checkpoint path invokes the Jev hook | **pass** *(hook fires; no native replacement)* | `POST /session/ses_f04eb835…/summarize` → **HTTP 200 `true`**; audit row `feature=compaction, phase=context.checkpoint, outcome=abstain, details={"anchor_count": 2}` for that session. The four pre-existing messages are still present afterwards (summarize appended a new exchange rather than replacing history) — **no native history replacement is claimed** |
| 7 | Deterministic destructive-command denial against the disposable sentinel | **pass** | model ran `cmd /c rmdir /s /q "<workspace>\denial-20261002-125445-fona"` → tool error `Jev denied: Jev invariant blocked this operation (recursive_delete).`; no second command issued; directory and `SENTINEL.txt` verified present on disk afterwards with content `JEV_WINDOWS_SENTINEL_DO_NOT_DESTROY`; `deny` count in `jev stats` rose 1 → 3 (the other new deny is this session's own blocked `rmdir` attempt, see §7.3) |
| 8 | Plugin loads without errors (restated) | **pass** | covered by #1 |

### 5.1 Optional receipts observed as `abstain` / not observed

| Check | Result | Evidence |
| :--- | :--- | :--- |
| `chat.message` mutation persists and reaches the model | **abstain** | all four `turn.before` features returned `abstain`; the persisted user text part is byte-identical to the prompt (`Objective: verify Jev context injection on Windows OpenCode. Say OK and stop.`). No TypeSafe semantic client is configured on this boot, so features abstain and no part is mutated — the documented `semantic_unavailable` boundary. |
| System-tail (`experimental.chat.system.transform`) append renders | **not observed** | asked the model directly whether its system text carries a Jev block → it replied `NONE`. Consistent with an empty advisory queue plus abstaining features. |
| Semantic behaviour generally | **unavailable** | `reason_code: semantic_unavailable` on safety rows; deterministic path unchanged. |

## 6. Latency (Windows boot)

| Measurement | n | min | p50 | p95 | max |
| :--- | ---: | ---: | ---: | ---: | ---: |
| Interpreter cold start (`python -c pass`) | 10 | 60.5 ms | 66.7 ms | 78.6 ms | 78.6 ms |
| `python -m jev doctor` — the plugin's startup probe | 10 | 878.4 ms | 934.3 ms | 1034.4 ms | 1034.4 ms |
| `python -m jev hook --harness opencode`, safe `tool.execute.before` spawn round trip | 10 | 225.8 ms | 241.4 ms | 286.7 ms | 286.7 ms |
| `opencode --version` (what dominates doctor) | 5 | 632.4 ms | 640.3 ms | — | 674.5 ms |
| In-harness footer latency seen live | — | — | 250.0 ms | — | 266.0 ms |

- The hook spawn round trip lands at **p95 286.7 ms**, inside the RFC-24 §5.8 **≤ 300 ms** budget; live sessions use the persistent `jev hook-worker`, so this is the cold path, not the per-request cost.
- The startup probe costs ~0.93 s against its **3000 ms** budget, of which ~0.64 s is Node starting up for `opencode --version`.
- Observed footer latency is dominated by the **250 ms semantic timeout**; the deterministic safety decision itself is immediate.
- n=10 does **not** establish P95 for production traffic — same caveat RFC-27 already records for the three-sample Linux number.

## 7. Findings

**No code or config change was made.** No test and no live check exposed a defect inside the OpenCode/shared-runtime scope, so nothing was fixed. `git status --short` at the end is identical to the start, `git diff --check` exits 0, and nothing was committed.

1. **The task's literal pytest command cannot run on this machine** — `%TEMP%\pytest-of-user` is ACL-denied, giving 53 setup errors before any test body runs. Workaround: `--basetemp=<fresh directory outside the checkout>`. Environment issue, not a Jev defect; no test was edited.
2. **Git needs `safe.directory` for this checkout.** Handled per-invocation with `git -c safe.directory=D:/01_GIT/Jev` so the user's global git configuration was not modified.
3. **`POST /session/:id/summarize` changed in 1.18.34** — it now requires a JSON body carrying `providerID` (and `modelID`); without it the server answers `400 Missing key at ["providerID"]`. The RFC's Linux receipt used the bare call. The sibling `POST /api/session/:id/compact` answers `503 Session compact is not available yet` and is not a substitute. This is a documentation-level delta for RFC-27 §S5, not a Jev defect.
4. **`opencode debug config` takes no `--dir`** on this release; run it with the target workspace as the current directory instead.
5. **OpenCode version drifted** from the RFC's `1.18.32` to `1.18.34`. All §5.1 bindings used by the shim were re-verified against the live binary during these checks and still hold.
6. **`jev doctor` costs ~0.93 s on Windows**, dominated by `opencode --version`. Inside the 3 s probe budget; worth carrying into RFC-27 §5.8 if the probe ever gets tighter.
7. Pre-existing working-tree edits to `src/jev/adapters/antigravity.py` and `src/jev/adapters/codex.py` were left exactly as found — no cross-harness regression was reproduced, so the RFC's non-interference rule never widened the scope.

## 8. Final state

| Item | Value |
| :--- | :--- |
| `python -m jev doctor --cwd .` | `problems: []` |
| `opencode mcp list` | `✓ jev connected` |
| config / plugin SHA-256 | unchanged from start |
| `git status --short` | identical to starting state |
| `git diff --check` | exit 0 (one benign `CRLF will be replaced by LF` warning on `adapters/antigravity.py`) |
| Disposable workspace | removed after path confirmation; pytest basetemps removed; `opencode serve` on port 4899 stopped and port verified free |
| Commits | none |

## 9. What is still open

| Item | Status |
| :--- | :--- |
| Windows install → uninstall → reinstall round trip (RFC-27 S3 gate) | **not run** — Jev already installed and healthy; running it was explicitly not required and would only risk the user's integration |
| `chat.message` mutation that persists and reaches the model | **abstain** — blocked on a configured TypeSafe semantic client, not on Windows behaviour |
| System-tail append rendering | **not observed** — same root cause (empty advisory queue + abstaining features) |
| Larger latency sample for a real P95 | **not run** |
| Fresh Codex / Antigravity application sessions | **out of scope** for this receipt; RFC-27 tracks them separately |
| Linux revalidation of the current working tree | **not run** — Windows boot only |
