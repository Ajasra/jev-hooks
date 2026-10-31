# Cross-platform Acceptance Evidence Protocol

**Status:** Active
**Scope:** Jev proposals that change runtime behavior, harness adapters, registrations, tools, skills, persistence, or packaging.

## Purpose

Acceptance evidence should show which supported system and harness combinations were exercised, what each check observed, and what remains unknown. A test pass on one harness does not establish behavior in another.

Use the [`proposal-acceptance` skill](../skills/proposal-acceptance/SKILL.md) to apply this protocol to an implemented proposal. Harness-specific commands and UI steps stay in their platform runbooks under `docs/`.

## 1. Scope the verification matrix

Derive the test scope from the proposal's changed boundaries. Consider shared core, each changed adapter, lifecycle hooks, callable tools, native skills, storage, and installer or registration paths. Include only OS and harness combinations supported by the repository and affected by the change.

Keep one result per relevant OS/harness pair. Record combinations that are unsupported, unavailable, or out of scope explicitly; do not infer their result from another row.

## 2. Run checks in order

1. Read the proposal, applicable workspace instructions, targeted tests, and runbooks for the affected systems.
2. Record the starting revision, dirty worktree summary, runtime versions, and relevant configuration paths without exposing secrets.
3. Run focused offline tests for the changed boundary. Run broader suites only when the proposal, repository gates, or blast radius calls for them.
4. Run each required live sequence in the actual application and workspace. CLI replay, an MCP handshake, or another harness's result cannot stand in for native hook evidence.
5. After any implementation fix, repeat the affected focused checks and live steps.
6. Run the applicable doctor/diagnostic command, compare the final worktree with the baseline, and remove only the exact disposable artifacts created for the run.

## 3. Keep live checks safe

- Preserve existing user changes, registrations, MCP servers, policy, and authorization records. Do not reset, clean, stash, or overwrite them.
- Use a dedicated disposable directory and isolated test state. Test destructive policy only against a temporary target containing a known sentinel. Never use real workspace or personal data as the target, and never grant the test operation.
- Summarize registrations and configuration. Omit credentials, tokens, private prompts, and unrelated personal settings from receipts.
- If setup is missing or a check cannot run, record the exact blocker. Make a repair only after identifying a reproduced defect and keep it within the supported shared-core or native-adapter boundary.

## 4. Record evidence with provenance

Create or update `docs/testing/<proposal-or-scope>-acceptance.md`. Include:

- revision, starting dirty-tree summary, OS/runtime/application versions, and exact offline commands with counts;
- one matrix row per relevant OS/harness pair, with registration, workspace identity, required live actions, audit result, cleanup, and code/config changes;
- evidence source for each result: directly observed live run, CI, or user-supplied report;
- provider-dependent unavailable/abstain results, harness capability differences, and unresolved blockers.

Use only these result labels: **PASS**, **FAIL**, **BLOCKED**, **NOT RUN**, or **UNSUPPORTED**. A row passes only when its required observable evidence is present. A successful doctor or tool listing alone does not prove a live hook ran. User-supplied evidence may be recorded, but label its source.

## 5. Close the proposal honestly

Mark a proposal's acceptance complete only when every required matrix row passes or the proposal explicitly excludes the remaining rows with a documented rationale. Keep blocked, unsupported, and unrun coverage visible. Update proposal status only when the receipt supports the claim, and report verified results separately from remaining blockers.
