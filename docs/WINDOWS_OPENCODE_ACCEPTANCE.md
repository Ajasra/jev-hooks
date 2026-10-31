# Windows OpenCode Integration and Acceptance Task

Use this task from the Jev repository root in OpenCode. Read this file and `AGENTS.md` first, then complete the Windows acceptance work described below. Treat [RFC-27](proposals/RFC-27_CORE_opencode_harness.md) as the implementation contract and source of existing Linux evidence.

## Objective

Verify the current Jev integration with the installed Windows OpenCode application, close the outstanding Windows checks in RFC-27, and leave a concise, reproducible receipt. Make a code change only when a test or live check exposes a specific defect; keep fixes within the OpenCode/shared-runtime scope allowed by `AGENTS.md` and RFC-27.

## Repository and change safety

- Work from the Jev checkout root and use Windows commands through `cmd /c`.
- Begin by reading `git status --short` and `git diff --stat`. The checkout may contain in-progress user changes. Preserve them. Do not reset, clean, stash, checkout over, or reformat unrelated files.
- Read the Windows follow-up and pending checkboxes in RFC-27 before acting. RFC-27 includes historical Linux receipts and later Windows work; distinguish those explicitly.
- Keep Antigravity and Codex behavior stable. Do not edit `src/jev/adapters/antigravity.py` or `src/jev/adapters/codex.py` unless a reproduced cross-harness regression requires it. If it does, stop and report the evidence before broadening scope.
- Never run a destructive test against the user's project, home directory, or real data. For the live denial check, create a uniquely named disposable directory and sentinel under the disposable test workspace. Confirm Jev blocks the command and that the sentinel remains. Remove only that exact test directory after confirming its resolved path.
- Inspect the resolved OpenCode configuration and Jev ownership manifest before installing, uninstalling, or editing global configuration. Preserve unrelated values and existing plugins. Do not hand-edit `opencode.json` to force a green result. If the installer refuses a config it cannot safely parse or a plugin it does not own, leave it untouched and report the blocker.
- Do not expose API keys, tokens, private prompts, or full personal configuration in logs or the receipt.

## Work

1. **Capture the starting state.** Record the Jev revision, working-tree status, Python version, `opencode --version`, and the current Jev/OpenCode install and doctor status. Save a sanitized copy or hash of any config file that an install/uninstall round trip may touch; never include secret values. Do not assume the RFC's prior Windows state is still current.

2. **Run offline checks first.** Run the focused OpenCode adapter, render, install, doctor, shared-runtime, worker, and deadline tests. Then run the full Python suite and the executable plugin smoke test below. Record exact commands and pass/skip/fail counts. Investigate failures against the starting tree; do not dismiss baseline failures or edit tests only to make the run pass.

   ```cmd
   cmd /c python -m pytest -q tests/test_opencode_adapter.py tests/test_opencode_render.py tests/test_opencode_install.py tests/test_opencode_doctor.py tests/test_shared_runtime.py tests/test_hook_worker.py tests/test_client_deadline.py
   cmd /c python -m pytest -q
   cmd /c npm exec --yes --package=tsx -- tsx tests/opencode_plugin_smoke.ts
   ```

   If a named test file is absent in the current checkout, report that fact and continue with the files that exist. Do not install persistent global tooling. The `npm exec` command should use its ephemeral package behavior; if the project cannot execute it without changing a lockfile or project configuration, stop and report the exact failure.

3. **Check install and doctor behavior.** Run Jev's doctor for OpenCode and inspect its reported config directory, plugin ownership, skills path, MCP registration, interpreter, and version. If registration is missing, use the supported Jev installer from the checkout and record its output. Restart OpenCode after a config change. Confirm `opencode mcp list` reports Jev connected. Verify that existing user plugin, provider, permission, agent, model, and unrelated config entries remain unchanged.

   ```cmd
   cmd /c python -m jev doctor --cwd .
   cmd /c python -m jev install opencode --cwd .
   cmd /c opencode mcp list
   ```

   Run the installer only if inspection shows it is needed. If Jev is already installed, do not reinstall just to exercise the command. Only run `python -m jev uninstall opencode` as part of an explicitly planned round-trip after recording the config snapshot, and reinstall afterward so the user's original working integration is left available.

4. **Run live checks in a disposable workspace.** Use a temporary project outside the Jev checkout, start a fresh OpenCode session with that directory as the workspace, and keep any generated files there. Verify each item below through OpenCode and Jev's audit records (`python -m jev stats --harness opencode` or the equivalent supported command):

   - Jev startup/doctor probe completes and the generated plugin loads without errors.
   - A user turn reaches Jev context handling; recent objective/error context is bounded and does not leak across sessions.
   - A harmless command such as `echo JEV_WINDOWS_SAFE_OK` is allowed and leaves an OpenCode safety audit event.
   - A write/edit inside the disposable workspace succeeds.
   - Jev MCP tools are discoverable and at least `jev_skills_list` runs; OpenCode's `skill` tool can see and load a canonical Jev skill.
   - OpenCode's summarize/checkpoint path invokes the Jev hook. Record whether context was injected and whether the audit row appears; do not claim native history replacement.
   - The deterministic destructive-command denial is exercised only against the disposable sentinel described above. Confirm the command did not execute and the sentinel remains.

   Do not make live provider calls unless the required credentials are already configured and the check is necessary. If semantic behavior is unavailable without credentials, record `unavailable`/`abstain` and continue validating deterministic integration behavior.

5. **Check recovery and final state.** If an install/uninstall round trip is required, confirm Jev removes only its owned keys and plugin, restores all unrelated config byte-for-byte where applicable, then reinstall and restart OpenCode. Finish with doctor, MCP discovery, `git status --short`, and `git diff --check`. Do not commit changes.

## Acceptance evidence

Create or update `docs/testing/windows-opencode-acceptance.md` with the date, Windows/Python/OpenCode versions, Jev revision, starting and ending install state, exact commands, test counts, and a table of live checks with pass/fail/not-run plus concise receipts. Redact user paths when they reveal personal data and never include secrets. Link any code fixes and explain each failed or skipped check. Update the Windows-pending checkboxes in RFC-27 only when that specific check has evidence; retain the Linux receipts as separate evidence. Do not change RFC status to implemented if the Windows release gate remains open.

Finish your response with the receipt path, tests and live checks completed, code/config changes made, and any remaining blocker. Clearly separate verified results from checks that could not run.
