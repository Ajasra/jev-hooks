# System One Agent Balance & Anti-Bureaucracy Protocol

**Version**: 1.0.0  
**Scope**: Universal Protocol for Machine-Native System One Semantic Decision Models (TypeSafe AI Jev, Google Antigravity 2.0 Hooks)  
**Location**: `.agents/protocols/system-one-balance-protocol.md`  
**Referencing Skill**: [`.agents/skills/system-one-balance-protocol/SKILL.md`](../skills/system-one-balance-protocol/SKILL.md)  
**Related Proposals**: [Proposal 02](../../proposals/02_PROPOSAL_B_DYNAMIC_SKILL_DISPATCHER.md), [Proposal 04](../../proposals/04_PROPOSAL_D_SAFETY_AND_TOOL_ROUTER.md), [Proposal 21](../../proposals/21_PROPOSAL_SPECULATIVE_FAN_OUT_AND_CONFIDENCE_ARBITRATION.md), [Proposal 23](../../proposals/23_PROTOCOL_SYSTEM_ONE_AGENT_BALANCE_AND_ANTI_BUREAUCRACY.md)

---

## 1. Core Architectural Principle: "Augment, Don't Handcuff"

Machine-native System One semantic decision models (such as Jev) exist to grant generative foundation models (Gemini, Claude, GPT) **speed, contextual awareness, and deterministic safety barriers**.

They MUST NEVER treat the foundation model like a prisoner or a toddler.

```
       ┌────────────────────────────────────────────────────────┐
       │             THE SYSTEM ONE BALANCE SPECTRUM            │
       └────────────────────────────────────────────────────────┘
  
  [ BUREAUCRATIC COP ]                                    [ SUPERCHARGED COPILOT ]
  (ANTI-PATTERN)                                          (TARGET ARCHITECTURE)
  ───────────────────                                     ──────────────────────
  • Turn-1 amnesia                                        • Conversational recency awareness
  • Imperative tool lockouts (`DO NOT CALL TOOLS`)       • Calibrated advisory guidance
  • Paralyzing modal prompts on natural continuations     • Seamless execution of follow-ups
  • Complete skill starvation below 0.80 confidence       • Two-tier soft hints with clickable links
  • Confirmation fatigue on routine dev commands          • Invariant shield + safe dev tool fast-path
```

---

## 2. Invariant Rules of the Balance Protocol

### Invariant 1: Conversational Recency Awareness (Anti-Amnesia)
* **Requirement**: Pre-flight hooks evaluating developer prompt ambiguity or routing intent MUST include recent conversational recency (`Prior Turn Context`) in the evaluation state sent to Jev.
* **Invariant**: Never evaluate follow-up turns in isolation.
* **Benchmark**: Prompts like *"commit"*, *"apply changes"*, *"update docs"*, *"run tests"*, or *"fix it"* must be recognized as contextual continuations with **Ambiguity = 0.0**.

### Invariant 2: Calibrated Advisories, Not Imperative Lockouts (Anti-Paralysis)
* **Requirement**: Pre-flight hooks MUST NOT inject imperative tool bans (`DO NOT call grep`, `DO NOT call view_file`, `You MUST call ask_question and nothing else`).
* **Invariant**: Emit calibrated, contextual advisories that preserve the foundation model's common sense and discovery autonomy.
* **Advisory Template**:
  ```markdown
  [SPECULATIVE ARBITER ADVISORY: The user instruction '{user_prompt}' appears underspecified in isolation.
  If the preceding conversational context or current project state does NOT clearly identify the intended target,
  PREFER invoking `ask_question` to render an interactive clarification modal rather than wandering into unguided exploration.
  However, if the immediate prior conversation context already defines the target or action, proceed with standard intelligent execution.]
  ```

### Invariant 3: Two-Tier Progressive Disclosure (Anti-Cliff)
* **Requirement**: Avoid the "0.79 Confidence Cliff" where a relevant skill is withheld completely because confidence missed an arbitrary 0.80 threshold.
* **Two-Tier Thresholds**:
  1. **Tier 1 (High Confidence $\ge 0.80$)**: Ephemeral injection of the full `SKILL.md` body with active in-chat badge.
  2. **Tier 2 (Soft Hint $0.50 \le P < 0.80$)**: Ephemeral injection of a lightweight, non-bloating 1-line hint with a clickable markdown link to the skill file.

### Invariant 4: Invariant Safety vs Routine Velocity (Anti-Fatigue)
* **Requirement**: Confirmation modals (`force_ask`) must be strictly reserved for genuinely irreversible, high blast-radius actions.
* **Three-Stage Separation**:
  1. **Deterministic Invariant Shield**: Hard-block `git push --force`, `rmdir /s /q`, `rm -rf`, `DROP TABLE`. Non-bypassable.
  2. **Safe Fast-Path**: Workspace file modifications (`write_to_file`, `replace_*`) and standard developer tools (`git status`, `git commit`, `pytest`, `npm test`) execute with zero interactive confirmation.
  3. **Persistent SQLite Memory**: Developers can save permanent or session-scoped rules (`always` / `session`) to permanently suppress prompts for their specific workflows.

---

## 3. Protocol Verification Checklist

Before deploying any new lifecycle hook or proposal:

- [ ] Does the hook complete in $\le 300\text{ms}$ (P95)?
- [ ] Does the hook fail open safely if the API or network stalls?
- [ ] Does the hook ingest conversational recency before scoring ambiguity?
- [ ] Does the hook allow the foundation model to use read-only discovery tools?
- [ ] Does the skill router provide soft hints for moderate-confidence matches?
- [ ] Are safety confirmations reserved exclusively for irreversible actions?
