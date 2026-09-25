# Proposal 23: System One Agent Balance, Anti-Bureaucracy & Anti-Stupidity Protocol

**Status**: Implemented & Standardized  
**Target Harness**: Google Antigravity 2.0 / Universal Lifecycle Hooks  
**Core Model**: TypeSafe AI Jev (System One Semantic Decision Layer)  
**Related Proposals**: [Proposal 02](02_PROPOSAL_B_DYNAMIC_SKILL_DISPATCHER.md), [Proposal 04](04_PROPOSAL_D_SAFETY_AND_TOOL_ROUTER.md), [Proposal 18](18_ARCHITECTURAL_TREATISE_SYSTEM_ONE_ANTIGRAVITY.md), [Proposal 21](21_PROPOSAL_SPECULATIVE_FAN_OUT_AND_CONFIDENCE_ARBITRATION.md)  
**Standardized Skill**: [`system-one-balance-protocol`](../.agents/skills/system-one-balance-protocol/SKILL.md)

---

## 1. Executive Summary

As agentic harnesses integrate faster semantic micro-decision models (System One) to govern tool use, safety, and dynamic skills, a dangerous failure mode arises: **over-governance**. When System One models operate with turn-level amnesia or inject heavy-handed imperative lockouts (`[DO NOT CALL TOOLS]`), the agent is stripped of common sense and turned into a slow, bureaucratic obstacle.

This proposal formalizes the **System One Agent Balance Protocol**: a set of architectural invariants and telemetry schemas ensuring System One always **augments** the primary reasoning model rather than **handcuffing** it.

---

## 2. Failure Modes: How Bad Guardrails Make Agents Dumber

| Anti-Pattern | Manifestation | Root Cause | Net Impact |
| :--- | :--- | :--- | :--- |
| **Turn-1 Amnesia** | Flagging natural continuations (*"commit"*, *"apply changes"*, *"update docs"*) as vague. | Evaluating prompts in total isolation without trajectory recency. | Halts execution with unnecessary clarification modals; breaks flow. |
| **Imperative Lockouts** | Injecting *"DO NOT call grep or view_file"*. | Over-constraining foundation model autonomy during elevated ambiguity. | Paralyzes the model; prevents non-destructive exploratory discovery. |
| **Confidence Cliff** | Complete skill withholding at $P = 0.79$. | Hard binary threshold for progressive disclosure ($\ge 0.80$). | Model operates blind to relevant workflows and domain recipes. |
| **Confirmation Fatigue** | Prompting developer on routine test runs or harmless status checks. | Over-broad blast radius definitions in safety gates. | Developer blindly clicks *"Allow"* on all prompts, nullifying actual safety. |

---

## 3. The Four Core Pillars of Balanced Control

### 3.1 Pillar 1: Conversational Trajectory Recency
Every pre-flight hook evaluating ambiguity or intent must include the immediate conversational recency (`Prior Turn Context`) in its evaluation `state`:

```yaml
Project Identity: TypeSafe AI — Small units of AI intelligence for agentic software
Workspace Path: d:\01_GIT\Jev (Branch: master)
Active Agent: Autonomous Review & Test Engineer
Prior Turn Context: feat: support custom agent persona context in speculative router
Developer Prompt: update documentation if needed. commit
```

By presenting the immediate context, Jev evaluates whether the prompt is a **contextual continuation** (Ambiguity = `0.0`) or a **cold-start vague request** (Ambiguity = `2.0`).

### 3.2 Pillar 2: Calibrated Advisories, Not Imperative Lockouts
When ambiguity is genuinely high, System One hooks must emit **calibrated advisories**, not absolute tool bans:

* ❌ **Old Imperative Lockout**:
  ```markdown
  [CRITICAL AGENT INSTRUCTION: The user instruction is completely underspecified.
  DO NOT browse the workspace, explore random files, or speculate on hidden context.
  You MUST immediately invoke your ask_question tool. DO NOT call any other tools.]
  ```
* ✅ **New Calibrated Advisory**:
  ```markdown
  [SPECULATIVE ARBITER ADVISORY: The user instruction '{user_prompt}' appears underspecified in isolation.
  If the preceding conversational context or current project state does NOT clearly identify the intended target,
  PREFER invoking `ask_question` to render an interactive clarification modal rather than wandering into unguided exploration.
  However, if the immediate prior conversation context already defines the target or action, proceed with standard intelligent execution.]
  ```

### 3.3 Pillar 3: Two-Tier Progressive Disclosure (Soft Hints)
Instead of a single binary threshold, the dynamic skill router employs a two-tier disclosure mechanism:
1. **High Confidence ($\ge 0.80$)**: Injects full `SKILL.md` body ephemerally with the `> **Activated Skill**: ...` badge.
2. **Medium Confidence ($0.50 \le P < 0.80$)**: Injects a lightweight 1-line hint with a clickable link:
   ```markdown
   <skill_hint name='system-one-balance-protocol'>
   > [!TIP]
   > **Available Skill Hint**: `system-one-balance-protocol` may be relevant to this task (Confidence: 0.51).
   > If specialized workflows are needed, view its instructions at [system-one-balance-protocol](file:///path/to/SKILL.md).
   </skill_hint>
   ```

### 3.4 Pillar 4: Invariant Safety vs Routine Velocity
1. **Zero-Latency Invariant Shield**: Non-bypassable deterministic guards on irreversible data loss commands (`rmdir /s`, `rm -rf`, `git reset --hard`, `git push --force`).
2. **Safe Fast-Paths**: Workspace file mutations and standard developer tools (`pytest`, `git status`, `git commit`, `npm test`) pass instantly without prompting.
3. **Persistent SQLite Memory**: Allows developers to approve once per session or permanently, eliminating confirmation fatigue.

---

## 4. Verification and Compliance

All existing and future proposals must adhere to the checklist codified in [`.agents/skills/system-one-balance-protocol/SKILL.md`](../.agents/skills/system-one-balance-protocol/SKILL.md). Tests must explicitly verify that:
1. Routine follow-up turns do not trigger false ambiguity modals.
2. Moderate-confidence skills are surfaced as hints rather than dropped.
3. Hook latency remains $\le 300\text{ms}$ on P95.
