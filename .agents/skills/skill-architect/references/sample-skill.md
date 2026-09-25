# Antigravity & Jev Skill Template Blueprint

Every skill written, refactored, or audited by the Skill Architect must match this exact structure.

---
name: [kebab-case-name]
description: >
  A concise, 1-2 sentence explanation of what this skill accomplishes and exactly when the agent or dynamic router should activate it.
concerns: [system-one-balance]   # omit if no protocols needed; see mapping below
---

# [Title of Skill]

## Phase 0: Setup and Protocols
- Resolve protocols matching the `concerns` field using the mapping table at the bottom of this document.
- Review referenced protocols before generating or executing instructions.

## Phase 1: Ingest and Check
1. Validate required inputs, file paths, or target environment settings.
2. Specify exact fallback behavior or default paths if arguments are omitted.
3. Fail open gracefully on missing dependencies without crashing the harness.

## Phase 2: Processing (Core Logic)
- Structure workflow into sequential, numbered phases using active imperative verbs:
  - "Read", "Parse", "Verify", "Mutate", "Execute", "Report".
- Avoid vague conversational fluff or open-ended speculation.
- Keep context instructions compact to respect prompt budgets.

## Phase 3: The System One Balance & Anti-Bureaucracy Pass
- Scan generated workflow against [`.agents/protocols/system-one-balance-protocol.md`](../../protocols/system-one-balance-protocol.md).
- **Invariants**:
  - Does NOT shout imperative tool lockouts (`DO NOT CALL TOOLS`).
  - Does NOT interrupt routine user workflows with confirmation modals.
  - Keeps instructions mechanical and actionable.

## Phase 4: Output Execution & Verification
- Define exact output file paths, formats, and artifacts.
- Verify discovery via `jev_skill_router.py`:
  ```cmd
  cmd /c python .agents/hooks/jev_skill_router.py
  ```

---

## Concerns → Protocol Mapping

| Concern | Protocol File |
|:---|:---|
| `system-one-balance` | `.agents/protocols/system-one-balance-protocol.md` |
