---
name: doc-architect
description: Audits, standardizes, refactors, and authors documentation, READMEs, and technical RFC proposals using Progressive Disclosure and Vasily Betin's authorial voice. Use when reviewing or writing documentation, restructuring guides, or drafting proposals.
---

# Documentation & Proposal Architect (`doc-architect`)

> **Governing Protocols**:
> - [`.agents/protocols/documentation-standard-protocol.md`](../../protocols/documentation-standard-protocol.md)
> - [`.agents/protocols/style-protocol.md`](../../protocols/style-protocol.md)
> - [`.agents/protocols/anti-slop-protocol.md`](../../protocols/anti-slop-protocol.md)
> - [`.agents/protocols/system-one-balance-protocol.md`](../../protocols/system-one-balance-protocol.md)

This skill designs, audits, and refactors documentation across Jev. It enforces **Progressive Disclosure** (Human Front Porch $\rightarrow$ Practitioner Workshop $\rightarrow$ Engine Room), calibrates prose to Vasily Betin's authorial voice, and purges AI slop.

---

## Phase 0: Setup & Governing Protocols

Before reviewing or modifying documentation, verify:
1. **[Documentation Standard Protocol](../../protocols/documentation-standard-protocol.md)**: Governs reading hierarchy, audience boundaries, README line limits, and RFC taxonomy.
2. **[Authorial Style Protocol](../../protocols/style-protocol.md)**: Governs voice (Pragmatic Systems-Philosopher & Hacker-Artisan), preferred vocabulary, and tone.
3. **[Anti-Slop Protocol](../../protocols/anti-slop-protocol.md)**: Governs tell detection, cadence variance, and elimination of bureaucratic filler.
4. **[System One Balance Protocol](../../protocols/system-one-balance-protocol.md)**: Enforces non-blocking semantic advice and deterministic safety boundaries.

---

## Phase 1: Audience & Document Triage

Determine the role of the target document:

| Role | Primary Target | Primary Purpose | Tone & Constraints |
| :--- | :--- | :--- | :--- |
| **Root Front Door** | `README.md` | First impression, 60s quickstart, visual proofs, hub links | Punchy, visual, max **150 lines**. Zero duplicate theory. |
| **Conceptual Foundation** | `docs/PHILOSOPHY.md` | Deep conceptual home (Context Envelope, System 1 vs 2) | Systems-philosopher voice, relatable analogies, grounded in reality. |
| **Practitioner Workshop** | `docs/USER_GUIDE.md` | Daily operations, IDE modal interactions, CLI auditing | Action-oriented, terminal traces, clean commands. No duplicated philosophy. |
| **Engine Room** | `docs/ARCHITECTURE.md` | Machine contracts, ports & adapters, SQLite schemas | Rigorous, deterministic, complete specs & test harnesses. |
| **RFC Proposal** | `docs/proposals/RFC-XX_...` | Deep architectural blueprints and treatises | Progressive Disclosure: Front Porch $\rightarrow$ Developer Impact $\rightarrow$ Tech Spec. |

---

## Phase 2: The 3-Stage Progressive Disclosure Architecture

Ensure the document is structured for progressive disclosure:

```text
[Stage 1: The Human Front Porch]
  → What breaks? What hurts? What is the physical/systems intuition?
  → Anyone can read this in 2 minutes and grasp 100% of the concept.
       ↓
[Stage 2: The Practitioner's Workshop]
  → How do I use it? What does it look like in my terminal/IDE?
  → 60s installation, CLI commands, visual logs, modal behaviors.
       ↓
[Stage 3: The Engine Room]
  → How does it work under the hood?
  → IPC JSON contracts, SQLite schemas, P95 budgets, formal invariant proofs.
```

### Writing Rules:
- **No Duplication Across Documents**: If `docs/PHILOSOPHY.md` explains the 4-layer Context Envelope, `docs/USER_GUIDE.md` must link to it rather than copy-pasting three paragraphs of theory.
- **Stage-Appropriate Detail**: Keep machine contracts and raw JSON in Stage 3 (`ARCHITECTURE.md` or RFC specs), never in Stage 1.

---

## Phase 3: The Style & Anti-Slop Verification Pass

Before committing or presenting documentation:

1. **Voice Calibration Check**:
   - Does it sound like a pragmatic builder explaining an apparatus to a peer?
   - Are claims grounded in physical/computational mechanics (latency, memory, blast radius)?
   - Are corporate hype and empty academic filler completely absent?
2. **Anti-Slop Scan**:
   - Check against [`.agents/protocols/anti-slop-protocol.md`](../../protocols/anti-slop-protocol.md) and [`tells.md`](../anti-slop-editor/references/tells.md).
   - Strip negative parallelisms ("not X, but Y").
   - Eliminate symmetrical triad checklists.
   - Enforce cadence variance (no 3 consecutive sentences of identical word count).
3. **Portability & Formatting Invariants**:
   - All links must be relative (zero `file:///` local schemes).
   - All Windows shell commands must use `%CD%` and prefix with `cmd /c`.
   - Root `README.md` must not exceed 150 lines.
