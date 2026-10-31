# Windows Antigravity and Codex Acceptance Task

Run this task separately inside a fresh Antigravity session and a fresh Codex session, with the Jev checkout as the workspace. Read `AGENTS.md`, this file, [the user guide](USER_GUIDE.md), and [RFC-24](proposals/RFC-24_CORE_shared_harness_runtime.md) first. Each application must produce its own live evidence; success in one harness does not verify the other.

## Objective

Verify that the installed Windows Antigravity and Codex applications load Jev's current registrations, route events through the shared runtime, preserve workspace identity, expose Jev tools/skills, and apply their native safety outcome correctly. Record the two results in `docs/testing/windows-antigravity-codex-acceptance.md`.

This is acceptance work. Make code changes only to fix a specifically reproduced defect. Preserve the current worktree and keep any fix within shared core or native adapter boundaries in `AGENTS.md` and RFC-24.

## Safety and scope

- Begin by recording `git rev-parse HEAD`, `git status --short`, `git diff --stat`, `python --version`, `codex --version`, and the installed Antigravity version if the app exposes it. Compare the start/end working-tree state; the checkout contains user changes.
- Do not reset, clean, stash, commit, or overwrite user changes. Do not edit Jev policy or authorization records to make a test pass.
- Inspect the existing local and global registrations before changing anything. Preserve `%USERPROFILE%\.codex\hooks.json`, `%USERPROFILE%\.codex\config.toml`, dispatcher files, `%USERPROFILE%\.gemini\config\hooks.json`, junctions, MCP configuration, and unrelated MCP servers. If a registration is missing or broken, report the exact evidence before making a narrowly scoped supported repair. Never replace a complete user config file.
- For Codex, use a **new trusted session** after any hook/config change. The local Jev project hooks apply inside this checkout; a global Codex dispatcher must bypass the checkout to prevent duplicate dispatch. Confirm the effective `cwd` with `diagnostics_status`.
- For Antigravity, reload the application after any hook/config change. Verify that its installed hooks point to the Jev shared runtime through the expected global junction/bootstrap.
- Use only harmless actions plus one denial test in a temporary directory. Never test destructive behavior against the Jev checkout, home directory, or real data. Do not grant/approve the denial test.
- Do not expose credentials, tokens, private prompts, or full personal configuration in the receipt. Missing provider credentials mean semantic features may report `unavailable`/`abstain`; do not add credentials for this task.

## Offline checks

Run focused transport/runtime tests before live app work. The Windows OpenCode acceptance already ran the full suite on this tree; do not repeat it unless code changes during this task.

```cmd
cmd /c python -m pytest -q --basetemp="%TEMP%\jev-antigravity-codex-acceptance" tests\test_gate_integration.py tests\test_gate_eval.py tests\test_shared_runtime.py tests\test_hook_worker.py
```

If the basetemp already exists, use a new unique name. Record the exact command and counts. If pytest encounters the known `%TEMP%\pytest-of-user` ACL failure, keep the explicit basetemp and report the environment error. If a named test is missing, report it and continue with files that exist; do not modify tests simply to get a green result.

## Checks to run in each application

Run each sequence once in Antigravity and once in Codex, in separate fresh sessions. The live app must perform the test action so its actual hook registration is exercised; CLI replay or MCP connectivity alone is not sufficient.

1. **Registration and startup:** confirm the application starts without a Jev hook/extension error. Antigravity should load its Jev hook registration; Codex should show Jev's project hook review as trusted and load the repository `.codex/hooks.json`. Record the app's exact version when available.
2. **Runtime identity and tools:** call `diagnostics_status` and `skills_list` (or `jev_skills_list` if that is the advertised tool name). Confirm the reported harness is `antigravity` or `codex` as appropriate, `workspace_root` resolves to this Jev checkout, there are no registration problems, and the canonical skill count is reported. In Codex, also run `codex mcp list` from a terminal and confirm Jev is connected if the user-global MCP registration is configured.
3. **Turn hook:** submit a harmless task-specific prompt and confirm Jev records a turn event for the correct harness/workspace. Check the audit view with:

   ```cmd
   cmd /c python -m jev stats --harness antigravity
   cmd /c python -m jev stats --harness codex
   ```

   Run only the matching command for the app under test. If semantic features abstain due to unavailable credentials, record that; the event still needs to show that the live hook reached Jev.

4. **Harmless tool call:** have the live app run `cmd /c echo JEV_WINDOWS_HARNESS_OK` (or the harness's equivalent harmless command). Confirm it executes and Jev records an `allow` for the correct harness. For Codex, verify the native hook output uses Codex's `hookSpecificOutput` envelope. For Antigravity, verify its native decision/context response is accepted without a hook error.
5. **Workspace file edit:** ask the app to create and read back a small uniquely named text file inside the repository's disposable test directory. Remove only that exact test artifact after confirming its path and recording the result.
6. **Deterministic denial:** in a temporary subdirectory under a disposable test directory, create `SENTINEL.txt` with known contents. Ask the live app to run `cmd /c rmdir /s /q "<exact temporary subdirectory>"`. Antigravity may present its native confirmation UI: record the Jev prompt and cancel it. Codex should return Jev's denial through its native hook response. In both cases confirm the target still exists and the sentinel contents are unchanged. Never authorize this test.
7. **Native skills and MCP:** verify the app can discover the canonical Jev skill catalog and load one skill if its native skill surface supports it. For Antigravity, confirm the configured `mcpServers.jev` connection and call `skills_list` or `jev_skills_list`. For Codex, confirm native skill discovery from the repository `.agents/skills` path and call Jev's MCP tool when available. Record any harness capability difference instead of treating it as a Jev failure.
8. **Final audit and cleanup:** inspect `jev stats --harness <current-harness>` again and confirm the expected safe allow and denial appear under the matching identity. Remove only the confirmed disposable test directory. Start a second clean session only if needed to distinguish session-scoped context; never infer isolation from an event that lacks session/workspace identity.

## Recovery and changes

If hooks do not load, first capture the app's exact error and resolved registration path. Do not reinstall or replace global configuration speculatively. Check the shared runtime's `jev doctor` result and compare the relevant registration with the repository's canonical `.agents/hooks.json`, `.codex/hooks.json`, and `.codex/config.toml`. Apply only a supported, minimal repair after identifying the failed binding, then restart/reload the affected app and repeat its acceptance sequence.

Run `cmd /c python -m jev doctor --cwd .` before and after. Run `git status --short` and `git diff --check`; no unrelated change should appear. Do not commit.

## Receipt

Create or update `docs/testing/windows-antigravity-codex-acceptance.md` with separate Antigravity and Codex sections. Include the Windows/Python/app versions, Jev revision and starting dirty-tree summary, exact focused test command/counts, effective hook/MCP registration (summarized without secrets), workspace identity, one row per live check with pass/fail/blocked/not-run, relevant audit evidence, any code/config change, and cleanup status. Clearly mark provider-dependent behavior as unavailable when appropriate.

Update RFC-24 or other acceptance status only when the corresponding live evidence exists. Do not claim that all Windows harnesses are verified if either application lacks a receipt. Finish by reporting verified results and remaining blockers separately.
