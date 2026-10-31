# Linux OpenCode Revalidation Task

Run this task from the Jev checkout root on the Linux boot. Read `AGENTS.md`, this file, [Linux global setup](LINUX_SETUP.md), and [RFC-27](proposals/RFC-27_CORE_opencode_harness.md) first. Revalidate the current checkout against the Linux machine's installed OpenCode. Windows results are useful comparison data, but do not count as Linux receipts.

## Objective

Close RFC-27's Linux revalidation gate for the current tree. Run focused and full offline tests, the executable plugin smoke test, then repeat the live OpenCode S5 smoke matrix in a disposable workspace. Record the evidence in `docs/testing/linux-opencode-revalidation.md` and update RFC-27 only for checks supported by that evidence.

This is acceptance work. Make a code change only when a check reproduces a specific defect. Preserve the current working tree and keep any necessary fix within the OpenCode/shared-runtime scope in `AGENTS.md` and RFC-27.

## Safety and scope

- Start with `git status --short`, `git diff --stat`, `git rev-parse HEAD`, `python3 --version`, `opencode --version`, and the installed Jev/OpenCode doctor status. Record the exact starting revision and dirty-tree summary. Compare them with `docs/testing/windows-opencode-acceptance.md` so both receipts clearly identify the tested tree.
- The checkout contains in-progress user work. Do not reset, clean, stash, checkout over, or reformat unrelated files. Do not commit.
- Preserve the Linux user's global OpenCode config, plugin list, MCP servers, and skills. Inspect the resolved config and Jev ownership manifest before any install/config action. Run `jev install opencode` only if doctor proves the registration is missing and the supported installer can safely handle the existing config. If it refuses JSONC, an unowned plugin, or an ownership mismatch, stop that action and report the blocker. Do not hand-edit global config.
- Do not repeat the install/uninstall cycle: RFC-27 already has Linux round-trip evidence. Do not rerun the Windows checks.
- Run live behavior only in a newly created temporary workspace outside the Jev checkout. All generated files and the destructive-command sentinel must stay there. Confirm the resolved path before cleanup, then remove only that exact workspace.
- Never test deletion against the Jev checkout, home directory, or real user files. Do not reveal credentials, tokens, private prompts, or full personal config in the receipt.
- Missing provider credentials must remain an `unavailable`/`abstain` result. Do not add credentials to global settings for this task.

## Offline checks

Use the checkout's Linux environment (`.venv-linux/bin/python`). If it does not exist, inspect the existing environment first and follow `LINUX_SETUP.md`; do not overwrite an existing virtual environment. Create pytest's temporary directory outside the checkout so test artifacts do not pollute the working tree.

```bash
PYTEST_BASE="$(mktemp -d /tmp/jev-opencode-focused.XXXXXX)"
.venv-linux/bin/python -m pytest -q --basetemp="$PYTEST_BASE" \
  tests/test_opencode_adapter.py \
  tests/test_opencode_render.py \
  tests/test_opencode_install.py \
  tests/test_opencode_doctor.py \
  tests/test_shared_runtime.py \
  tests/test_hook_worker.py \
  tests/test_client_deadline.py
```

```bash
PYTEST_BASE="$(mktemp -d /tmp/jev-opencode-full.XXXXXX)"
.venv-linux/bin/python -m pytest -q --basetemp="$PYTEST_BASE"
```

```bash
npm exec --yes --package=tsx -- tsx tests/opencode_plugin_smoke.ts
```

Record the exact results, including skips. The broken-worker lines emitted by the plugin smoke test are expected only when the test's deliberate broken-instance assertion passes; inspect the command's final exit status and success message. Do not install persistent global Node tooling or allow the smoke check to change tracked manifests/config. If a named test file or dependency is missing, record that and report the actual failure rather than silently changing project setup.

## Installed integration check

Run the doctor and MCP checks using the project environment:

```bash
.venv-linux/bin/python -m jev doctor --cwd .
opencode mcp list
```

Record `opencode --version`, doctor problems, Jev config/plugin ownership, MCP connection, interpreter path, and the resolved OpenCode config directory. Run `opencode debug config` from the disposable workspace if this version supports it; record plugin origins and load errors without dumping secrets or the complete user config. If Jev is already installed and healthy, leave it in place.

## Live smoke matrix

Create a unique disposable project outside the checkout, start a fresh OpenCode session rooted there, and use that session for these checks. Inspect Jev's records with `.venv-linux/bin/python -m jev stats --harness opencode` or the available harness-specific audit view.

1. **Startup probe and plugin:** the generated Jev plugin loads without errors; the startup doctor/worker probe succeeds.
2. **Turn context:** a user turn produces Jev `turn.before` audit rows. Check context anchors are bounded and isolated to the workspace and session. Record `abstain` accurately if semantic inference is unavailable.
3. **Safe shell:** run `echo JEV_LINUX_SAFE_OK`; confirm it completes and a `safety / tool.before / allow` record exists.
4. **Workspace edit:** write a small sentinel text file inside the disposable project and read it back.
5. **MCP and skill discovery:** confirm Jev MCP is connected; call `jev_skills_list`; have OpenCode's `skill` tool load one canonical Jev skill.
6. **Checkpoint hook:** exercise OpenCode's summarize/checkpoint path and confirm a Jev `context.checkpoint` audit row. Record the context result; do not claim native history replacement.
7. **Destructive denial:** create a uniquely named sentinel file under a uniquely named subdirectory inside the disposable project. Ask the live OpenCode agent to run a recursive delete command against that exact subdirectory. Confirm Jev denies it and the sentinel still exists with unchanged contents. Remove it only during final cleanup after recording evidence.
8. **Session/workspace isolation:** if the preceding checks provide enough events, confirm audit and saved context rows retain the disposable workspace/session identities and do not mix with another workspace. If the event set cannot establish this, record `not verified` rather than infer a pass.

Use the summarize API supported by the installed OpenCode version. Version 1.18.34 requires `providerID` and `modelID` in `POST /session/:id/summarize`; older RFC receipts used a bare request. Inspect the live OpenCode version/route and active session model before calling it. Never send made-up provider/model values just to trigger the hook. If a legitimate summarize operation cannot be initiated, report that item as blocked and retain the existing Linux receipt as historical evidence only.

Do not attempt optional semantic injection probes that require provider access unless credentials are already available through the normal Linux setup. RFC-27's Linux S0 spike receipts already cover plugin protocol mutation and system-tail rendering; this task revalidates the current Jev integration and S5 behavior.

## Final state and receipt

Run doctor and MCP discovery again. Confirm the temporary workspace is removed, OpenCode processes started for this task are stopped, no global config/plugin changed unexpectedly, and no unrelated tracked or untracked work was altered. Run `git status --short` and `git diff --check`; compare status with the starting snapshot.

Create or update `docs/testing/linux-opencode-revalidation.md` with the date, Linux distribution/kernel if available, Python/OpenCode versions, Jev revision and starting dirty-tree summary, exact test commands and counts, install/doctor evidence, a pass/fail/blocked/not-run row for every live check, config/plugin change summary, and cleanup result. Redact personal paths and omit secrets. Clearly distinguish this current-tree receipt from RFC-27's older Linux evidence and the Windows receipt.

Update RFC-27's dual-boot suite and live S5 gate only after the matching Linux evidence is written. Keep every unverified item open, including any Windows-specific S0/S3 gate that remains pending. Do not change RFC status or claim both platforms are complete while a required gate is open.

Finish by reporting the receipt path, exact tests and live checks completed, any changes made, and all remaining blockers. Separate verified results from historical evidence and unavailable checks.
