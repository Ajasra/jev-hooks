---
name: proposal-acceptance
description: >
  Builds and runs a scoped acceptance matrix for an implemented Jev proposal across affected operating systems and agent harnesses.
  Use after proposal implementation when offline, live application, or cross-harness evidence needs to be collected and recorded.
concerns: [system-one-balance]
---

# Proposal Acceptance

Apply the [Cross-platform Acceptance Evidence Protocol](../../protocols/cross-platform-acceptance-protocol.md). Use the repository's existing platform runbooks for native commands and UI steps.

## Phase 0: Setup and Protocols

1. Read the active proposal, repository `AGENTS.md`, the acceptance evidence protocol, and applicable test/runbook documentation.
2. Read the current `git status --short`; preserve pre-existing changes and identify the files this task may add or update.
3. Treat a new OS/harness combination as in scope only when the proposal affects it and Jev declares support for it.

## Phase 1: Map the change

1. Trace changed behavior to its shared core, adapters, registry entries, storage, packaging, and native registrations.
2. Select focused tests and live checks that observe those boundaries. Include every affected supported OS/harness pair; skip unrelated pairs with a reason.
3. Create a matrix before testing:

   | OS | Harness | Changed boundary | Offline checks | Live checks | Status |
   |---|---|---|---|---|---|

4. Resolve each row to an existing runbook under `docs/`. If none exists, record the missing runbook as a gap and use the protocol's common evidence fields without inventing harness behavior.

## Phase 2: Run offline checks

1. Record the starting revision, OS, Python/runtime versions, application versions when available, and a concise dirty-tree summary.
2. Run the smallest relevant existing tests first. Use isolated temporary storage where tests could touch Jev state. Do not repeat a known full-suite run unless the change or repository gate requires it.
3. Save exact commands, exit status, and test counts. Record environment failures as blocked; do not change tests to manufacture a pass.

## Phase 3: Run live acceptance

For each required OS/harness row:

1. Use a fresh or reloaded native application session as the runbook requires. Confirm startup and the effective registration path.
2. Call diagnostics and skill/tool listing when available. Verify harness identity and that workspace root resolves to the intended checkout.
3. Trigger the changed lifecycle behavior from the native application, then inspect the harness-filtered audit evidence. A CLI replay or MCP connection check alone does not count as a live hook test.
4. Exercise a harmless allow path when relevant. Verify the harness-native response contract where the feature depends on it.
5. For changes to safety policy or tool interception, run one denial probe against an exact disposable target with a sentinel. Never approve it; verify the target remains unchanged.
6. For changed file, skill, or callable-tool behavior, verify the applicable native discovery or invocation path.
7. Label each row **PASS**, **FAIL**, **BLOCKED**, **NOT RUN**, or **UNSUPPORTED**, and cite the observed evidence and source. Record provider-unavailable behavior as unavailable/abstain.

If a defect appears, capture the exact failure before editing. Make only an in-scope fix, then rerun affected offline and live checks.

## Phase 4: Receipt and verification

1. Write results to `docs/testing/<proposal-or-scope>-acceptance.md`, keeping one section/table row per OS/harness pair. Include versions, revision, exact test commands/counts, registrations, workspace identity, audit evidence, cleanup, and any changes.
2. Separate directly observed results from CI and user-supplied evidence. Never convert a missing observation into a pass.
3. Run the relevant doctor command, `git diff --check`, and final `git status --short`. Confirm pre-existing changes remain and remove only exact disposable artifacts created by this run.
4. Update proposal acceptance status only when required rows have supporting receipt evidence. End with verified results and remaining blockers.

## Phase 5: System One Balance

- Keep the workflow scoped to evidence needed for the proposal; do not demand every platform for an unrelated change.
- Let routine read-only inspection and harmless tests proceed without extra approval steps.
- Keep deterministic safety checks and native application permissions authoritative. Never weaken policy to get a passing receipt.
