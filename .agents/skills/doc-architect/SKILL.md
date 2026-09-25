---
name: doc-architect
description: Audits, standardizes, refactors, and authors user-faced and dev-faced documentation, READMEs, and technical RFC proposals using the human-centric narrative template and unified taxonomy. Use when asked to review or write documentation, re-architect READMEs, or draft and unify architectural proposals.
---

# Documentation & Proposal Architect (`doc-architect`)

This skill operationalizes the canonical [Documentation & Proposal Standards Protocol](../../protocols/documentation-standard-protocol.md). It ensures that all project documentation, README files, user guides, architecture treatises, and RFC proposals adhere to the human-centric narrative template, strict audience segmentation, and unified taxonomy without information loss or cognitive bloat.

---

## Phase 0: Setup & Governing Protocols

Before reviewing or modifying any documentation, verify and load the foundational protocols:
1. **[Documentation Standard Protocol](../../protocols/documentation-standard-protocol.md)**: Governs narrative flow, audience boundaries, README limits, and RFC taxonomy.
2. **[System One Balance Protocol](../../protocols/system-one-balance-protocol.md)**: Governs anti-bureaucracy, calibrated advisories, and anti-bloat principles.

---

## Phase 1: Audience & Document Triage

Determine the category of the document being audited, authored, or refactored:

| Category | Primary Target File | Core Audience | Primary Purpose | Tone & Constraints |
| :--- | :--- | :--- | :--- | :--- |
| **Root Hub** | `README.md` | New users, evaluators, developers | First-impression value, 60s quickstart, visual proof gallery, navigation hub | Engaging, visual, max **150 lines**. No CLI command dumps. |
| **User-Faced** | `docs/USER_GUIDE.md` | Application developers using Jev | Practical onboarding, IDE modal responses, rule database CLI, `.env` configuration | Practical, task-oriented, clear steps. Zero low-level IPC schemas. |
| **Dev-Faced** | `docs/ARCHITECTURE.md` | Hook authors, contributors | Machine-native hook contracts, IPC (stdin/stdout), SQLite schema, latency budgets | Rigorous, deterministic, complete specs & test harnesses. |
| **RFC Proposal** | `proposals/RFC-XX_...` | System architects & reviewers | In-depth architectural proposals, patterns, and treatises | Structured RFC: Human narrative block + Technical Specification. |

---

## Phase 2: The 5-Step Human Narrative Flow

Every document (README, User Guide, Architecture Spec, RFC) must open with the human-centric narrative sequence before diving into technical arcana:

```text
[1. Problem]       → What hurts, breaks, or wastes tokens in current agent harnesses?
       ↓
[2. Inspiration]   → Biological reflex, Kahneman System 1/2, microkernel OS, eBPF, prior art.
       ↓
[3. Solution]      → How Jev non-autoregressive primitives or native hooks solve it.
       ↓
[4. Example]       → Real before/after trace, terminal log, screenshot, or concrete metrics.
       ↓
[5. Technical Deep Dive] → Schemas, IPC payloads, database models, CLI commands, test suites.
```

### Writing Rules for Sections:
* **Problem**: Anchor in concrete pain points (e.g., *"Loading 50 skills consumes 15,000 tokens on every turn"*, *"Accidental rmdir /s cannot be undone"*).
* **Inspiration**: Give intuitive metaphors (reflexes vs deliberation) so non-specialists understand the design intuition.
* **Solution**: Highlight calibrated probabilities, sub-120ms P95 latency, and zero schema validation failures.
* **Example**: Show tangible visual or tabular proof (e.g., ASCII log, modal screenshot, or test table).
* **Technical Details**: Keep deep details in dedicated sections or secondary files, never in the opening fold.

---

## Phase 3: The System One Balance & Anti-Bloat Pass

When refactoring or auditing documentation:

1. **Information Preservation Invariant**:
   * **Never delete critical decisions or technical specifications.**
   * When trimming the root `README.md`, extract CLI reference tables and IPC specs into `docs/USER_GUIDE.md` or `docs/ARCHITECTURE.md`.
2. **Git-Compatible Relative Links Invariant**:
   * All file links must be strictly relative to the markdown file's directory (e.g. `../.agents/protocols/...`, `./RFC-01...`).
   * **NEVER** use absolute `file:///` local URI schemes or hardcoded drive letters (`C:\`, `D:\`), ensuring links render portably on GitHub and any clone path.
3. **Portable Shell Commands (`%CD%` & `cmd /c`)**:
   * In setup instructions, NEVER hardcode local developer workspace paths. Use dynamic `%CD%` paths (e.g., `cmd /c mklink /J "%USERPROFILE%\.gemini\config\hooks" "%CD%\.agents\hooks"`).
   * All shell executions on Windows must include the mandatory `cmd /c` prefix for clean process termination.
4. **Length Enforcement**:
   * The root `README.md` must not exceed **150 lines**. If it exceeds 150 lines, identify sections to extract into `docs/`.

---

## Phase 4: Proposals (RFC) Taxonomy & Master Index Sync

When creating, renaming, or refactoring RFC documents in `proposals/`:

1. **Standard Filename Pattern**:
   $$\mathbf{RFC\text{-}\langle ID\rangle\_\langle CATEGORY\rangle\_\langle slug\rangle.md}$$
   - Categories: `CORE` (hooks), `USE_CASE` (industry patterns), `FOUNDATION` (treatises/inspiration), `EXT` (extensions/linters/speculation), `GUIDE` (setup), `PROTOCOL` (balance rules).
   - Example: `RFC-01_CORE_verbatim_context_compactor.md`
2. **Standard RFC Header**:
   ```markdown
   # RFC-XX: [Title]

   > **Category**: [CATEGORY]  
   > **Status**: [Implemented | Blueprint | Catalog | Case Study]  
   > **Target Lifecycle**: [PreInvocation | PreToolUse | Session GC | CI/CD | Harness Core]  
   ```
3. **Master Catalog Synchronization**:
   * Always verify that [`proposals/README.md`](../../../proposals/README.md) indexes the RFC with its exact title, status, category, and working clickable link.
