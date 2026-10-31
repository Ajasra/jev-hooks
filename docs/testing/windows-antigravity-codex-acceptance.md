# Windows Antigravity and Codex Acceptance Receipt

Date: 2026-10-02 (Asia/Shanghai)

Scope: Windows acceptance for Codex and Antigravity. Codex evidence was collected in this task; Antigravity evidence below was supplied by the user after the Codex run.

## Baseline

- Windows: Microsoft Windows [Version 10.0.26300.9550]
- Python: 3.10.9
- Codex CLI: `codex-cli 0.156.1`. A separate desktop build version was not exposed by this session.
- Antigravity version: not included in the supplied acceptance summary.
- Jev HEAD at start: `bca82bb245389dc3ccdcef516878f33b11b71d47`
- Starting worktree: 25 modified tracked paths and 11 untracked paths. Changes already covered runtime, adapters, tests, and docs; this receipt is added under the pre-existing untracked `docs/testing/` directory. No existing changes were reset or overwritten.
- Focused command: `cmd /c python -m pytest -q --basetemp="%TEMP%\jev-antigravity-codex-acceptance-20261002" tests\test_gate_integration.py tests\test_gate_eval.py tests\test_shared_runtime.py tests\test_hook_worker.py`
- Focused result: **28 passed in 5.43s**.
- The same focused command was separately reported for Antigravity as **28 passed in 4.73s** using `%TEMP%\jev-antigravity-codex-acceptance` as basetemp.
- `python -m jev doctor --cwd .` before and after: `workspace_root` resolved to `D:\01_GIT\Jev`, `problems: []`, and no rejected project keys.
- `git diff --check`: exit 0; only reported the existing CRLF-to-LF warning for `src/jev/adapters/antigravity.py`.

## Codex

Effective registration observed:

- Repository `.codex/hooks.json` defines `SessionStart`, `UserPromptSubmit`, and `PreToolUse` hooks invoking `python -m jev hook --harness codex`; `PreToolUse` matches `Bash|apply_patch|mcp__.*`.
- Repository `.codex/config.toml` defines the Jev MCP server with `python -m jev mcp --cwd . --harness codex`.
- User-global `%USERPROFILE%\.codex\hooks.json` points the same lifecycle events to `%USERPROFILE%\.codex\hooks\jev_dispatch.cmd`; the dispatcher and global config are present. The global config's Jev MCP entry is enabled. `codex mcp list` reported `jev` enabled. No configuration was changed.
- The live Jev `skills_list` tool returned **7 canonical skills**, with paths under `D:\01_GIT\Jev\.agents\skills`. Codex project configuration points native skill discovery to that repository source.
- The live session produced no visible startup hook error. The deterministic denial below confirms the Codex `PreToolUse` hook was active.

| Check | Result | Evidence |
|---|---|---|
| Registration/startup | PASS | Repository and user-global Jev registrations present; active Codex session showed no Jev startup error. CLI version: 0.156.1. |
| Runtime identity and workspace | BLOCKED | `diagnostics_status` reported `harness_identity: codex` and Jev `package_root`, but `workspace_root` was `C:\Users\user\AppData\Local\OpenAI\Codex\bin\be3fd7e5c1969ff6`, not the Jev checkout. The local `jev doctor --cwd .` independently resolves the checkout correctly with no problems. The live root mismatch remains unresolved. |
| Turn hook and audit | PASS, aggregate only | `jev stats --harness codex` showed 1,157 Codex events before live checks and 1,180 after; no per-action event/session identifiers are exposed by this summary. Semantic provider behavior was not separately evaluated. |
| Harmless tool call | PASS | The live Codex task ran `cmd /c echo JEV_WINDOWS_HARNESS_OK`; output was `JEV_WINDOWS_HARNESS_OK`. Aggregate `allow` count rose from 736 to 754. The hook response envelope was not separately captured. |
| Workspace file edit/read | PASS | Created `tests\_jev_codex_acceptance_20261002\edit_case\codex-proof.txt` and read back `Codex acceptance workspace file`. |
| Deterministic denial | PASS | Attempt to run `cmd /c rmdir /s /q "D:\01_GIT\Jev\tests\_jev_codex_acceptance_20261002\deny_case"` was blocked by native PreToolUse: `Jev invariant blocked this operation (recursive_delete)`. The command was not approved. `SENTINEL.txt` remained and contained `JE V SENTINEL PRESERVE`. Aggregate deny count rose from 40 to 41. |
| Native skills and MCP | PASS | Jev MCP was enabled in `codex mcp list`; `skills_list` returned 7 canonical skills rooted in `.agents\skills`. |
| Final audit and cleanup | PASS | Final summary: 1,180 Codex events; 754 allow, 41 deny, 376 abstain, 9 needs_confirmation. Removed only the exact acceptance `codex-proof.txt`, sentinel, and temporary directories. No permission records or credentials were changed. |

Workspace identity discrepancy note: diagnostics and doctor disagree about `workspace_root`. Since the active tool's reported root is outside the checkout and global/local registration repair would be speculative, no configuration repair was made. The exact event-to-session correlation and Codex-native allow envelope were not available in the aggregate evidence.

Code/config changes: none. Receipt only.
Provider-dependent behavior: not assessed; no credentials were added or changed.

## Antigravity

Evidence source: user-provided acceptance summary (not independently re-run in this Codex session).

| Check | Result | Evidence |
|---|---|---|
| Registration/startup | PASS, user-reported | Antigravity loaded `%USERPROFILE%\.gemini\config\hooks.json` via the junction to `D:\01_GIT\Jev\.agents\hooks`; bootstrap resolved to the Jev checkout. |
| Runtime identity and tools | PASS, user-reported | `diagnostics_status` reportedly returned package root `D:\01_GIT\Jev` and `problems: []`; all 7 canonical skills under `.agents\skills` were verified. |
| Turn hook and audit | PASS, user-reported | `turn.before` handlers for knowledge, skills, speculative, and knowledge_proposer fired. Events were associated with workspace `89774075d76ca7207d00ebb8` and session `a5e05538-c6b2-4691-a7b6-46a792d3dc15`. |
| Harmless tool call | PASS, user-reported | `cmd /c echo JEV_WINDOWS_HARNESS_OK` executed; Jev recorded allow with `semantic_unavailable → deterministic_fallback`. |
| Workspace file edit/read | PASS, user-reported | `.tmp_acceptance\step5_test.txt` was created, read back, and deleted. |
| Deterministic denial | PASS, user-reported | Jev intercepted recursive deletion of `.tmp_acceptance\denial_target` with `recursive_delete`; audit row 18424 was deny and `SENTINEL.txt` remained intact. |
| Native skills and MCP | PASS, user-reported | Canonical skills were discoverable and a skill such as `anti-slop-editor/SKILL.md` was inspectable. |
| Final audit and cleanup | PASS, user-reported | Reported telemetry: 17,093 total events, 2,401 allow, 10 deny. Disposable directories were removed; `jev doctor --cwd .` passed with zero problems; pre-existing changes were preserved. |

The supplied summary did not include an Antigravity app version. Its aggregate telemetry is recorded as reported and is not assumed to be Codex-specific.

## Remaining blockers

1. Resolve why live `diagnostics_status` reports the Codex runtime bin directory as `workspace_root` while `jev doctor --cwd .` reports `D:\01_GIT\Jev`; repeat diagnostics in a fresh trusted Codex session with confirmed effective `cwd`.
2. Capture action-level audit identity and the native Codex allow envelope if full event correlation is required.
3. The supplied Antigravity summary lacks the app version and was not independently re-run here; retain that provenance when citing dual-harness acceptance.
