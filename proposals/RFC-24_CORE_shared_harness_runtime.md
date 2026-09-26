# RFC-24: Shared Jev Runtime for Antigravity and Codex

> **Category**: CORE  
> **Status**: Implemented  
> **Target Lifecycle**: Harness Core  
> **Scope**: One implementation of each Jev feature, delivered to both harnesses.

## 1. Problem

Jev currently combines semantic decisions, Antigravity JSON contracts, filesystem discovery, and persistence inside hook scripts. Adding Codex by copying those scripts would make every feature change a two-implementation maintenance task. Shared log and debounce files also lack a harness identity.

The goal is to implement each hook, callable tool, and skill once. Antigravity and Codex must consume the same release, configuration model, feature registry, and business logic. Their adapters translate protocol details and expose verified capabilities.

The implementation covers the shared package, adapters, registrations, database, compatibility wrappers, offline tests, and documentation. It does not automatically change installed global hooks or migrate a live database. Automatic replacement of either harness's internal context remains outside the first release.

## 2. Inspiration

Use ports and adapters: feature code consumes a stable internal event and returns a stable result. The surrounding runtime handles storage, model requests, deadlines, and transport. Each harness has a small translation layer.

## 3. Solution

Keep `.agents/` canonical for authored skills, protocols, and repository knowledge. Move Python logic into an installable `jev` package. Generate harness registrations from one feature registry. Distribute the same package to both harnesses.

Architectural invariants:

- `jev/core/` has no Codex or Antigravity event keys, tool aliases, paths, or imports.
- Adapters contain decoding, encoding, lifecycle mapping, and capability declarations. Scoring, thresholds, authorization policy, retrieval, and routing remain shared.
- A feature using an existing portable event or tool interface requires no adapter code change.
- A new native lifecycle capability may require adapter work. Unsupported behavior is reported explicitly; installation never claims parity it cannot provide.
- Harness sandboxing and native approval policy remain authoritative. Jev permission memory records Jev policy, not a grant of operating-system or harness privileges.

## 4. Concrete Example

A developer adds a `test_failure_summary` handler and registers it for `tool.after`. Both adapters normalize their tool results into the same event. The handler creates a bounded summary, and each adapter returns it through its supported context channel. If a harness cannot deliver post-tool context, the same handler remains callable as a tool and the capability report labels the automatic trigger unavailable.

A new callable `knowledge.search` tool gets one handler and one JSON input/output schema. The shared tool server exposes it to both harnesses. A new skill gets one `.agents/skills/<name>/SKILL.md`; installation or packaging exposes that authored file to both.

## 5. Technical Specification

### 5.1 Package and source layout

```text
pyproject.toml
jev.json                         # project configuration, no secrets
src/jev/
  __main__.py                    # CLI entry point
  contracts.py                   # typed event/result/schema versions
  registry.py                    # single feature/tool registry
  runtime.py                     # dispatch, deadlines, aggregation
  core/
    safety.py
    skills.py
    speculative.py
    knowledge.py
    compaction.py
  adapters/
    base.py
    antigravity.py
    codex.py
  services/
    client.py                    # TypeSafe/OpenRouter boundary
    paths.py
    storage.py
    context.py
    process.py
  transports/
    mcp.py                       # shared callable tools
  install/
    render.py                    # native registration generation
    doctor.py
    templates/
.agents/
  AGENTS.md
  hooks/                         # temporary legacy import/CLI wrappers
  skills/                        # canonical authored skill sources
  protocols/
  knowledge/
tests/
  core/
  adapters/
  fixtures/antigravity/
  fixtures/codex/
  integration/
```

Use Python 3.10+ to preserve the available local runtime, with standard-library dataclasses, JSON, pathlib, sqlite3, and urllib for the core. Keep MCP as an optional dependency extra using the official Python MCP SDK v2; lock an exact tested release during implementation. Its documented minimum is Python 3.10. Core hooks must run without that extra. Avoid writing a custom MCP protocol stack. [Official MCP Python SDK](https://py.sdk.modelcontextprotocol.io/)

### 5.2 Shared contracts

`Event` carries `schema_version`, `event_id`, `kind`, `harness`, `harness_version`, `workspace_id`, `session_id`, optional `turn_id`, optional `agent_id`, optional `tool_call_id`, `cwd`, `timestamp`, `deadline`, and a typed payload.

Portable kinds are `session.start`, `turn.before`, `tool.before`, `tool.after`, `context.checkpoint`, and `session.end`. Internal commands such as `knowledge.learn` are callable actions, not invented native lifecycle events.

Payloads distinguish `ShellOperation`, `FileMutation`, and `ToolInvocation`. Preserve shell dialect, working directory, affected file paths, and raw tool identity for diagnostics. Do not treat an entire patch as a shell command. Unknown tool arguments remain structured and are never discarded or automatically classified as routine.

`Result` contains a policy outcome (`abstain`, `allow`, `deny`, `needs_confirmation`), a reason code, bounded context items, optional typed tool data, and timing/error metadata. `allow` means Jev has no objection; it does not bypass native restrictions. The first release does not rewrite pending tool arguments.

Adapters validate event-specific fields and emit only supported native output. A missing field stays unknown rather than becoming an empty shared session or a fabricated successful inspection. Raw transcripts, when available, are a versioned best-effort context source. Missing recency disables ambiguity-driven pressure to clarify.

### 5.3 Registry and execution

Each `FeatureSpec` declares a stable ID, version, handler, portable triggers, required capabilities, priority, deadline class, context budget, failure policy, and optional callable tool schema. Use explicit trusted registration in Python; project JSON cannot import arbitrary modules.

The same registry drives runtime dispatch, generated hook registrations, tool discovery, compatibility reports, and tests. Generate one dispatcher registration per native event where practical, avoiding three independent model requests and repeated context discovery for one turn.

Run deterministic safety before optional model scoring. Aggregate policy outcomes in the order `deny > needs_confirmation > allow > abstain`; advisories cannot weaken a decision. Use stable feature ordering and bounded context aggregation. Optional independent enrichment may run concurrently within one deadline; never execute workspace tests as speculative context collection.

Native invocation IDs are preferred for deduplication. Where unavailable, the adapter must establish a verified identity strategy before enabling deduplication. Repeated identical prompts are separate turns. Do not use a global prompt hash or an empty session ID as a debounce key. Persist atomic claims keyed by harness, workspace, session, agent, invocation, feature, and phase, with expiring leases after crashes.

Store the normalized result atomically with claim completion and any single-use authorization consumption. Redelivery of the same invocation replays that result, including denial. A new tool attempt gets a new identity and evaluation. An active claim may be awaited within the deadline; it never produces default allowance. Recovery after an expired lease re-evaluates incomplete work. Include the operation digest and policy version in cache validation so changed commands or policy cannot reuse an old allowance.

### 5.4 Harness mappings and capability limits

| Portable operation | Antigravity adapter | Codex adapter |
| --- | --- | --- |
| `turn.before` | Existing `PreInvocation`, guarded to initial invocation | `UserPromptSubmit` |
| `tool.before` | Existing `PreToolUse` | `PreToolUse` |
| Context delivery | Existing `injectSteps` representation | Supported `additionalContext` representation |
| Startup/after-tool/end | Verify against installed runtime before enabling | Map documented events and verify installed runtime |
| `needs_confirmation` | Existing `force_ask`, subject to contract verification | Supported denial with explanation; never emit unsupported `ask` |
| Context checkpoint | Shared sidecar storage with verified trigger or explicit command | Shared sidecar storage through verified lifecycle trigger or explicit command |

Codex currently rejects unsupported `PreToolUse` ask output and can continue execution after that hook error. `PermissionRequest` only handles an approval already being requested. Therefore unsupported mandatory confirmation must prevent execution rather than silently degrade to allow. Ordinary actions continue without Jev prompts. The existing conflict between protocol hard-denial and implementation confirmation is resolved in shared policy: protocol invariants deny; conditional risky operations use `needs_confirmation`. Add documented policy-change tests before rollout. [Official hook contract, checked 2026-09-26](https://learn.chatgpt.com/docs/hooks)

For a denied conditional operation, a user may explicitly record a narrowly scoped Jev authorization and retry. That record includes operation identity, workspace, harness, expiry, and single-use state; it cannot override an invariant or native approval. Accept a verified native approval receipt where available. Otherwise provide a manual user-facing authorization command outside the published agent tool surface, showing the pending operation digest before granting it. Never expose permission grants through MCP or tell the agent to run the grant command. A local CLI is an operational workflow, not a security boundary against arbitrary same-user processes; native sandbox controls remain essential. If user provenance cannot be established, keep the conditional action denied and show manual recovery instructions. Existing Antigravity confirmation integration remains only where actual approval feedback can be verified. The legacy `--allow` entry point must not gain trusted provenance merely by being called.

Capability status is `verified`, `unsupported`, or `unverified`, tied to harness version and a smoke-test receipt. Required unsupported capabilities prevent activation of the affected feature. Optional ones produce a declared fallback. Hook coverage is a supplemental guardrail, not a complete execution boundary.

### 5.5 Configurable directories

For ordinary discovery and advisory settings, resolve configuration in this order: CLI override, `JEV_*` environment, project `jev.json`, user configuration, platform defaults. Resolve relative configured paths against their defining file. Secrets come from environment or an explicitly selected secret file; do not scan arbitrary workspace `.env` files by default.

Trusted installation configuration owns policy floors, harness identity, authorization provenance, and the rules-store path. Project files and agent-supplied tool arguments cannot override these settings. An explicit user installation change may relocate trusted storage; routine event invocations cannot. Project settings may narrow discovery roots or reduce advisory work, but cannot weaken invariants or choose a fresh authorization database. Validate configuration provenance before applying precedence and report rejected overrides through doctor.

Separate `package_root`, `workspace_root`, `config_root`, `data_root`, `cache_root`, `skill_roots`, and `knowledge_roots`. Derive workspace identity from the canonical checkout path; preserve separate worktree identities. A repository identity may separately group shared knowledge. Use path-aware containment, including Windows case rules and symlink resolution, rather than string-prefix matching.

Default shared mutable state: `%LOCALAPPDATA%/Jev` on Windows, platform user-data directories on macOS/Linux. Both local harnesses point to the same explicit `data_root` when shared storage is desired. Sandbox-constrained installations use a permitted root and report when it is isolated. Installed package directories remain read-only.

Keep authored skills in `.agents/skills`. Configurable global roots may include current Antigravity locations and Codex user skill locations. Native discovery and Jev routing share the catalog; avoid injecting a full skill body twice. Package builds copy canonical sources into required distribution paths and verify content hashes. Generated copies are never edited manually.

### 5.6 Shared SQLite database, separate harness logs

Use one local `jev.sqlite3` by default, with `harness` required on every event. Provide `codex_events` and `antigravity_events` views and CLI filters, allowing separate reports and combined analysis without separate schemas.

Tables:

- `schema_migrations`: schema version, migration identity, applied time.
- `events`: event ID, harness/version, workspace, session/agent/turn/tool IDs, feature/version, phase, outcome, reason code, source, duration, timeout/error flags, redacted details.
- `rules`: policy scope, harness scope, workspace scope, operation matcher, decision, provenance, creation/expiry, and explicit authorization metadata.
- `invocations`: deduplication claims, operation digest, policy version, lease expiry, completion, normalized replay result, and retry status.
- `session_context`: bounded recency/checkpoints, freshness and source references, keyed by harness/workspace/session/agent.
- `feedback`: exact event reference and user feedback, avoiding updates to an unrelated latest event.

Logs always retain origin. Durable knowledge may be shared with provenance; session context and temporary approvals never cross harnesses. Existing rules migrate as Antigravity-only. New rules default to the current harness and workspace; cross-harness policy sharing requires explicit scope.

Use transactions, WAL on supported local filesystems, bounded lock waits, indexes for harness/workspace/time and session correlation, and retention controls. A failed audit write must not turn a denial into allow. Rules-store failure falls back to deterministic policy without treating unavailable rules as authorization. Do not log credentials or full prompts/commands by default. Redaction precedes persistence and model requests; bounded diagnostic capture is opt-in.

Shared SQLite is local to one machine; reject network-filesystem WAL deployment and use independent databases on remote hosts. Record and validate the bundled SQLite version in doctor against the current supported/fixed release set before enabling concurrent WAL use. [SQLite WAL constraints](https://sqlite.org/wal.html)

### 5.7 One tool implementation and one skill source

Expose shared callable actions through a single MCP server generated from the registry. First tools: `knowledge.search`, `knowledge.learn`, `skills.list`, and `diagnostics.status`; mutation actions stay explicitly invoked. Both harness configurations point to the same server entry point. Tool requests resolve trusted workspace scope from installation/session bindings or validated roots, never an unrestricted caller-provided path. Capture harness origin through separately configured launch identity rather than trusting a model argument.

Hooks and MCP handlers call the same core services. External callable tools cannot bypass core policy because they skipped a hook. Verify both clients' MCP discovery and invocation in the compatibility matrix before declaring tool parity.

Skills use harness-neutral instructions and portable Jev tool/CLI names. Harness-specific invocation guidance belongs in generated setup instructions. Adding a skill requires no Python edits. Adding a tool requires one handler, schema, and registry entry. Adding a hook requires one handler, event subscription, and capability/failure declaration.

### 5.8 Compaction, deadlines, and error behavior

Keep compaction selection as a shared pure function. Its supported common product is a sidecar checkpoint with references to preserved source artifacts. Do not overwrite active Codex transcript files or claim sidecar compression reduces model context. Retain legacy offline compaction behind an explicit command. Native history replacement stays disabled until a harness exposes a verified contract.

Target P95 total added synchronous latency of 300 ms on the documented reference machine, including process startup, storage, and model calls. This is an acceptance target to measure, not a current guarantee. Pass one monotonic deadline through the dispatcher; record cold and warm timings separately. Give optional enrichment a 300 ms wall-time budget and return available context on expiry. Background knowledge learning runs only through explicit invocation in the first release.

Provider outage drops optional context and leaves native execution policy intact after deterministic checks. Safety cannot lose an already-established denial on timeout. Malformed safety input must produce a supported blocking error when an operation cannot be inspected; malformed advisory input produces no advisory. Terminate timed-out child processes and their descendants through the platform process service. JSON alone goes to hook stdout; diagnostics go to stderr and bounded logs.

## 6. Implementation Sequence

| Milestone | Work | Observable completion |
| --- | --- | --- |
| M0: Baseline and contracts | Capture sanitized real events, installed versions and approval behavior for both harnesses. Isolate all test DBs and network calls. Document capability matrix. | Existing supported Antigravity behavior has fixtures; Codex fixtures match native schemas; tests cannot touch live rules. |
| M1: Package and paths | Add Python package, configuration resolver, injected client/storage/process services, CLI and doctor. | Runs from checkout, installed package, subdirectory and paths containing spaces; no hardcoded Gemini paths outside migration/adapters. |
| M2: Core extraction | Move existing feature logic once; preserve old scripts as delegating wrappers. Add registry and event/result contracts. | Old Antigravity fixtures invoke shared core with equivalent results, except explicitly tested policy corrections. |
| M3: Database migration | Add schema and harness filtering; migrate a copy of legacy data transactionally; replace JSON debounce with atomic claims. | Row counts/provenance preserved, migration repeatable, concurrent harness sessions isolated, rollback rehearsal passes. |
| M4: Dual adapters | Implement Codex mapping and capability validation; consolidate Antigravity mapping. Translate confirmation behavior explicitly. | Equivalent normalized operations produce identical core decisions; supported native outputs are accepted by both live harnesses. |
| M5: Shared tools and skills | Add optional MCP transport, canonical catalog and generated registrations/packages. | A new sample tool, hook and skill each become available in both harnesses without editing either adapter. Unsupported-event test is reported clearly. |
| M6: Rollout and docs | Installer dry-run, selective config merge, backups, doctor, latency measurement, user guide and architecture updates. | Both harnesses enabled together in a test profile, upgrade/uninstall restores owned entries only, end-to-end acceptance matrix passes. |

M0 precedes implementation claims about native coverage. M1-M2 precede adapter rollout; M3 precedes live state migration. M4-M5 are both required for the shared-extension promise. M6 publishes one versioned release for both harnesses. No milestone automatically changes the user's global configuration.

## 7. Validation and Release Gates

- Unit-test shared policy, retrieval, routing, path resolution, redaction and deadline behavior with deterministic providers.
- Replay both native fixture sets through decode -> shared core -> encode. Compare semantic outcomes rather than native JSON equality.
- Test shell chains, PowerShell/cmd differences, patch content containing dangerous-looking strings, unknown tools and malformed payloads.
- Test concurrent worktrees and harnesses, equal native session IDs across harnesses, missing identifiers, duplicate delivery, legitimate repeated prompts and lease recovery.
- Test denied-event redelivery, crashes before claim completion, authorization redelivery, altered operation digests, and policy-version changes. Test a hostile project configuration attempting to replace trusted storage or weaken policy.
- Test DB lock/disk failure, API timeout, missing credentials, missing recency, unsupported hooks, read-only installs and partial migration.
- Run real smoke tests in both installed harnesses: startup context, prompt context, harmless tool allowance, controlled denied command, explicit tool invocation, and a newly registered feature.
- Verify native restrictions remain effective even when Jev returns allow. Verify neither adapter emits an unsupported confirmation output.
- Package/install tests verify generated skill hashes, command quoting, UTF-8 IPC, selective configuration ownership and version reporting. Windows is the first live target; Linux/macOS resolver tests do not imply live harness support.
- CI forbids harness-specific imports and event keys in core, checks registry-generated manifests for drift, and requires a compatibility declaration for every feature.

Tests run in temporary storage with network disabled by default. Live provider benchmarks are a separate opt-in suite. In particular, replace the current integration test's default-database `clear_all_rules()` before running it as part of the baseline.

## 8. Migration, Rollback, and Risks

Back up legacy SQLite through its backup API, including a consistent snapshot when WAL is active. Import into a separate versioned database, verify integrity and counts, and leave the original untouched. Map legacy records to Antigravity; preserve unmappable rules as disabled records requiring review rather than widening permissions. Stop hook writers during cutover and record the cutover timestamp. No unsafe dual-writing.

Use the [SQLite backup API](https://sqlite.org/backup.html) rather than copying only a live database's main file.

Legacy wrappers load the new package during a documented transition release. Generated registration files use an installer ownership manifest and hashes. Dry-run shows additions, removals and conflicts; never replace unrelated global hooks. Package or hook-definition updates may require native trust review. [Codex package and hook installation](https://developers.openai.com/plugins/build/plugins)

Rollback restores the previous owned registrations and runtime with its original database. New logs remain as a separate audit archive. Rules changed after cutover require explicit reconciliation; do not silently discard them or copy broadened permissions backward. Uninstall removes owned registration entries and leaves user knowledge and databases intact.

Largest risks are native lifecycle differences, unsupported confirmation UI, stale permission migration, and cold-start latency. The release gate is measured behavior on both harnesses. If a trigger is unavailable, retain the shared callable feature and report the missing automatic integration.

## 9. Decisions and Evidence

The implementation chooses shared source, thin adapters, a registry, configurable roots, and one harness-tagged database. Separate feature implementations and per-harness database schemas are rejected because they duplicate behavior and migrations. A custom harness fork is unnecessary for the supported first-release features.

Repository evidence:

- [Current registration](../.agents/hooks.json): Antigravity tool matchers, event names and global paths.
- [Safety gate](../.agents/hooks/jev_safety_gate.py): mixed event decoding, policy, HTTP and output encoding.
- [Database](../.agents/hooks/safety_db.py): shared Gemini path; rules and feedback lack harness identity.
- [Skill router](../.agents/hooks/jev_skill_router.py): duplicated catalog call and global debounce state.
- [Speculative router](../.agents/hooks/jev_speculative_router.py): transcript assumptions and synchronous pytest prefetch.
- [Compactor](../.agents/hooks/jev_compactor.py): in-place trajectory writes.
- [Integration tests](../tests/test_gate_integration.py): real default rules database mutation.

Codex sources checked on 2026-09-26: [hook contracts](https://learn.chatgpt.com/docs/hooks), [native skill discovery](https://learn.chatgpt.com/docs/build-skills), and [plugin packaging](https://developers.openai.com/plugins/build/plugins). Existing Antigravity code describes the intended integration; M0 must verify it against the installed harness before claiming runtime compatibility.

No further product decision is required to begin M0. Exact installed harness versions and native capability coverage are discovery outputs, not assumptions.

## 10. Independent Review and Changes

An isolated reviewer examined the initial full RFC and its code/documentation references. The architecture was sufficiently concrete to begin M0, with three major gaps corrected in this version:

| Finding in initial draft | Evidence | Correction |
| --- | --- | --- |
| Deduplication did not specify decision replay | Section 5.3 defined claims and leases only | Atomically persist results and authorization consumption; replay identical invocations; test crash and redelivery paths. |
| Project configuration could override trusted storage | Section 5.5 applied one precedence order to all settings | Separate ordinary settings from trusted policy, identity, and rules-store configuration. |
| Explicit user authorization lacked a defined channel | Section 5.4; existing `safety_db.py` CLI accepts `--allow` | Require verified native receipts or a documented manual workflow; exclude grants from MCP; state same-user process limitations. |

The review preserved the shared registry, thin adapters, canonical skill sources, harness-tagged database and reversible rollout. A local runtime check also changed the Python baseline to 3.10. These changes refine the implementation contract without changing the requested dual-harness scope.
