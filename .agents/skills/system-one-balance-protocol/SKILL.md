---
name: system-one-balance-protocol
description: Architectural protocol and guidelines for balancing System One micro-decisions with System Two reasoning to prevent agent paralysis, confirmation fatigue, and over-gating.
---

# System One Agent Balance & Anti-Bureaucracy Protocol

This skill codifies the architectural rules for integrating fast System One decision models (such as Jev) with large generative coding agents (such as Google Antigravity, Gemini, or Claude).

---

## 1. The Core Philosophy: "Augment, Don't Handcuff"

System One exists to give the primary foundation model **superpowers**, not to treat it like a prisoner or a toddler.

* **Good System One (Augmentation)**:
  * Arrives at Turn 1 with relevant evidence already prefetched (git diffs, test summaries, ast outlines).
  * Guards catastrophic, irreversible destruction (`rmdir /s`, `git reset --hard`) at zero latency.
  * Dynamically activates domain skills ephemerally to keep prompts lean.
  * Prunes repetitive 10,000-line build dumps to 300-char receipts while keeping code and errors 100% verbatim.

* **Bad System One (Bureaucracy)**:
  * Second-guesses natural conversational continuations (*"apply changes"*, *"commit"*, *"update docs"*).
  * Shouts imperative commands like `[CRITICAL INSTRUCTION: DO NOT CALL ANY TOOLS]`.
  * Paralyzes the agent with interactive clarification modals on prompts that preceding turns already made clear.
  * Causes "confirmation fatigue" by prompting the user on routine, benign developer tools.

---

## 2. The Four Pillars of Balanced Control

### Pillar 1: Conversational Trajectory Recency
**Rule**: Never evaluate developer prompts in complete amnesia.
* **Mechanism**: Every pre-flight hook evaluating ambiguity or intent MUST include recent conversational recency (`Prior Turn Context`) in its evaluation state.
* **Rationale**: Prompts like *"commit"*, *"run tests"*, or *"apply changes"* are ambiguous in isolation, but 100% explicit within a multi-turn conversation.

### Pillar 2: Calibrated Advisories, Not Imperative Lockouts
**Rule**: Never forbid foundation models from using basic discovery tools unless preventing an irreversible destructive write.
* **Mechanism**: When ambiguity is elevated, inject a strong **advisory** (*"Prefer asking for clarification if target is unknown..."*) rather than an absolute tool ban (*"DO NOT call view_file, grep, or run_command"*).
* **Rationale**: Foundation models have strong contextual synthesis. If they have enough context to proceed safely, let them proceed.

### Pillar 3: Two-Tier Progressive Disclosure (Soft Hints)
**Rule**: Avoid the "0.79 Confidence Cliff".
* **High Confidence ($\ge 0.80$)**: Inject full `SKILL.md` body ephemerally.
* **Medium Confidence ($0.50 \le P < 0.80$)**: Inject a lightweight 1-line hint with a clickable link:
  ```markdown
  > [!TIP]
  > **Available Skill Hint**: `app-security` may be relevant to this task (Confidence: 0.72).
  > View instructions at [app-security](file:///path/to/skill/SKILL.md) if needed.
  ```
* **Rationale**: The agent remains aware of relevant recipes without prompt token bloat.

### Pillar 4: Invariant Safety vs Routine Velocity
**Rule**: Reserve interactive confirmation modals strictly for high blast-radius, irreversible actions.
* **Mechanism**:
  1. **Deterministic Invariant Shield**: Hard-block `git push --force`, `rmdir /s /q`, `rm -rf`, `DROP TABLE`. Non-bypassable.
  2. **Fast-Path Allow**: Safe workspace file operations (`write_to_file`, `replace_*`) and routine dev commands (`pytest`, `git status`, `git commit`, `npm test`) must execute with zero friction.
  3. **SQLite User Memory**: Allow the developer to save persistent permissions (`always` / `session`) so they are never asked twice for the same routine command pattern.

---

## 3. Checklist for Future Proposals and Hooks

When designing a new hook, tool router, or System One evaluation:

- [ ] Does this hook add value in $\le 300\text{ms}$?
- [ ] Does this hook work gracefully if Jev is unreachable (fail-open policy for non-destructive actions)?
- [ ] Does this hook consider prior turn context before declaring a request ambiguous?
- [ ] Does this hook preserve user velocity without triggering confirmation fatigue?
- [ ] Is output tagged semantically (e.g. `<system_preflight_hook name="...">`) so LLMs treat it as trusted harness telemetry?

---

## 4. Canonical Specification Document

The full architectural protocol, design spectrum, and formal telemetry schemas are maintained in:
* **Workspace Protocol**: [`.agents/protocols/system-one-balance-protocol.md`](../../protocols/system-one-balance-protocol.md)
* **Global Linked Protocol**: `~/.gemini/config/protocols/system-one-balance-protocol.md`
* **Architectural Blueprint**: [`proposals/RFC-23_PROTOCOL_system_one_balance.md`](../../../proposals/RFC-23_PROTOCOL_system_one_balance.md)
