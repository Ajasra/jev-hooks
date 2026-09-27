# Jev Machine-Native Semantic Control: Architecture Specification

> **Audience**: Hook authors, systems architects, and framework contributors
> **Status**: Production Standard (Unified Shared Runtime)
> **Harnesses**: Google Antigravity 2.0 & OpenAI Codex
> **Foundational Philosophy**: [The Philosophy of Jev](PHILOSOPHY.md)
> **Related Protocols**: [Documentation Standard](../.agents/protocols/documentation-standard-protocol.md) | [System One Balance](../.agents/protocols/system-one-balance-protocol.md)

---

## 1. Architecture Overview: Ports and Adapters

Jev decouples agentic coding harnesses from semantic evaluation logic using a **ports-and-adapters** design. Harnesses (Google Antigravity, OpenAI Codex) act as external ports. Thin adapters translate native JSON payloads into harness-neutral `Event` and `Operation` contracts. The shared core owns safety evaluation, skill selection, speculative prefetching, and audit persistence.

```mermaid
flowchart LR
    A[Antigravity JSON] --> AA[Antigravity Adapter]
    C[Codex JSON] --> CA[Codex Adapter]
    AA --> E[Event + Operation]
    CA --> E
    E --> R[Shared Registry & Runtime]
    R --> S[Safety Gate]
    R --> SK[Dynamic Skills]
    R --> P[Speculative Context]
    R --> K[Knowledge Engine]
    S --> DB[(jev.sqlite3)]
    SK --> J[TypeSafe System One]
    P --> J
    K --> J
    R --> O[Result]
    O --> AA
    O --> CA
```

### Architectural Guarantees:
- **Authority belongs to determinism**: Invariant checks (regex, path traversal, hard resets) run locally in under 1ms without network calls.
- **Sub-120ms P95 semantic turnaround**: Non-autoregressive primitives (`Choice`, `Score`, `Noul`) return structured probability distributions without text generation overhead.
- **Fail-open on advisory timeouts**: Advisory checks have bounded deadlines (3.5s). If a semantic call times out or fails, workspace mutations proceed unblocked.
- **Zero policy drift**: A single shared SQLite database (`jev.sqlite3`) and identical safety rules govern both Antigravity and Codex.

---

## 2. Package Layout

The implementation root lives under `src/jev/`:

```text
src/jev/
  contracts.py       # Harness-neutral Event, Operation, Result, and Outcome definitions
  registry.py        # Central registration for FeatureSpecs and ToolSpecs
  runtime.py         # Lifecycle execution dispatcher
  core/
    safety.py        # Invariant Shield + blast radius evaluation
    skills.py        # Dynamic skill relevance ranking
    speculative.py   # Turn-1 diff and test log prefetching
    knowledge.py     # Repository Knowledge Item matching
    compaction.py    # Verbatim receipt context compactor
    semantic_lint.py # Architectural rule evaluation over git diffs
    verification.py  # API symbol and citation verification
  adapters/
    antigravity.py   # Translates Antigravity hook stdin/stdout JSON
    codex.py         # Translates OpenAI Codex hook payloads
  services/
    client.py        # Non-autoregressive TypeSafe / OpenRouter HTTP transport
    paths.py         # Cross-platform workspace path resolution
    storage.py       # Shared SQLite persistence & telemetry
  transports/
    mcp.py           # Shared MCP stdio server transport
  install/
    doctor.py        # Self-diagnostic engine
```

---

## 3. Portable Lifecycle Events

The runtime normalizes harness-specific triggers into portable lifecycle events:

| Event | Google Antigravity | OpenAI Codex | Description |
| :--- | :--- | :--- | :--- |
| `session.start` | *Unavailable* | `SessionStart` | Workspace and environment initialization. |
| `turn.before` | `PreInvocation` | `UserPromptSubmit` | Injects speculative diffs, skills, and knowledge into Turn 1. |
| `tool.before` | `PreToolUse` | `PreToolUse` | Intercepts proposed commands, file edits, and patches. |
| `tool.after` | *Reserved* | `PostToolUse` | Post-execution verification and telemetry logging. |
| `context.checkpoint` | Sidecar CLI command | `PreCompact` / `PostCompact` | Verbatim receipt pruning before context overflow. |
| `session.end` | *Reserved* | `SessionEnd` | Session cleanup and active learning checkpointing. |

Unknown or malformed inputs to safety hooks fail closed. Advisory hook errors fail open without injecting extra context.

---

## 4. Harness Capability & Behavioral Matrix

| Capability | Google Antigravity Binding | OpenAI Codex Binding | Implementing Module |
| :--- | :--- | :--- | :--- |
| **Safety Gate** | `PreToolUse` (renders interactive modal) | `PreToolUse` (emits permission deny) | `core/safety.py` |
| **Speculative Prefetch** | `PreInvocation` (injects prompt context) | `UserPromptSubmit` (`additionalContext`) | `core/speculative.py` |
| **Dynamic Skills** | Injects full body ($\ge 0.80$) or markdown link | Injects catalog ranking and hints | `core/skills.py` |
| **Knowledge Engine** | `PreInvocation` prompt injection | `SessionStart` & `UserPromptSubmit` | `core/knowledge.py` |
| **Output Verification** | `PreToolUse` non-blocking advisory context | `PreToolUse` `additionalContext` | `core/verification.py` |
| **Semantic Linting** | `prompt_user` advisory finding | `warn_user` advisory finding | `core/semantic_lint.py` |
| **Context Compactor** | Sidecar execution | Sidecar execution | `core/compaction.py` |
| **Audit Persistence** | `antigravity_events` view | `codex_events` view | `services/storage.py` |

### Key Transport Differences:
- **Interactive Approval**: Antigravity supports `"decision": "force_ask"`, prompting the developer directly in the IDE. Codex does not support interactive prompts at `PreToolUse`; conditional checks map to a clean denial with actionable reasoning.
- **Fail-Open Boundaries**: In both harnesses, workspace file mutations (`write_to_file`, `replace_*`, `apply_patch`) fail open if semantic inspection times out, ensuring developer flow is never blocked by network latency.

---

## 5. Safety Pipeline

When an agent proposes an action, the safety engine evaluates risks in strict order:

1. **Classification**: Identify operation type (file mutation, shell command, or structured tool invocation).
2. **Deterministic Shield**: Evaluate hard regex invariants (recursive deletion, force push, hard reset, disk partition commands). If violated, deny immediately without model invocation.
3. **Rule Database Lookup**: Check SQLite for existing workspace-, session-, or pattern-scoped authorizations.
4. **Semantic Blast Radius**: If unclassified and client is available, evaluate two parallel `Noul` questions (routine intent vs irreversible risk).
5. **Outcome Mapping**: Aggregate results via precedence:
   $$\mathbf{Deny} > \mathbf{NeedsConfirmation} > \mathbf{Allow} > \mathbf{Abstain}$$

Semantic advice cannot override a deterministic denial.

---

## 6. SQLite Schema & Active Learning

The audit store (`%LOCALAPPDATA%\Jev\jev.sqlite3`) uses WAL mode on local filesystems with bounded busy timeouts.

| Table / View | Description |
| :--- | :--- |
| `schema_migrations` | Idempotent schema migration log. |
| `events` | Master audit log tagged by harness, workspace, session, and tool. |
| `antigravity_events` | Partitioned view filtering Antigravity executions. |
| `codex_events` | Partitioned view filtering Codex executions. |
| `rules` | Learned policy memory and single-use CLI authorizations. |
| `invocations` | Atomic claim keys preventing duplicate execution replay. |
| `semantic_lint_decisions` | Historical evaluation logs for architectural lint rules. |
| `semantic_lint_feedback` | Developer confirmations or false-positive ratings. |

---

## 7. Extension Contract

`registry.py` provides the central extension point:

### Adding a Lifecycle Hook Feature:
1. Implement a harness-neutral handler in `src/jev/core/`.
2. Register a `FeatureSpec` declaring events, priority, execution budget, and failure behavior.
3. Add replay unit tests. Adapters only require updates if a harness introduces a new transport mapping.

### Adding a Callable Tool:
1. Add a typed handler to `src/jev/tooling.py`.
2. Register a `ToolSpec` in `registry.py`.
3. The shared MCP transport (`transports/mcp.py`) automatically discovers and exposes the tool to both Antigravity and Codex without per-tool transport configuration.

---

## 8. Verification & Test Harness

```cmd
cmd /c python -m pytest -q
cmd /c python -m jev doctor --cwd .
cmd /c git diff --check
```

The test suite validates cross-harness equivalence, replay denial, atomic single-use rule consumption, malformed JSON handling, and deterministic invariant barriers without requiring live network access.
