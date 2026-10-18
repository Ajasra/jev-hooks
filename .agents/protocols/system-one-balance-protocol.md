# System One balance protocol

Scope: designing JEV semantic hooks and decision surfaces. This document governs
hook design; it does not introduce a mandatory preflight for ordinary agent work.
User instructions and higher-priority harness policy govern permitted actions.

## Context and authorization

- Include the active objective, relevant prior turns, environment, and immediate
  failure evidence when available. Follow-ups often resolve from context, but
  several pending targets can still make “apply it” ambiguous.
- Emit actionable advice for semantic uncertainty. Preserve discovery tools and
  continue already-authorized work. Ask only about consequential unresolved choices.
- Evaluate command effects, target ownership, scope, reversibility, and existing
  authorization. Command spelling alone does not establish safety or permission.
  Cleanup of generated files differs from discarding user data; a test migration
  differs from dropping a production table.
- Preserve the runtime's deterministic safety floor. Skills cannot bypass harness
  blocks or relax policy through project configuration. If the floor is too broad,
  propose a centrally reviewed policy change rather than circumventing it.
- Save permissions only for the intended scope and context; changed targets or
  effects require reevaluation. Routine checks and authorized reversible edits
  should proceed without repeated confirmation.

## Routing and calibration

- Treat full-injection and hint thresholds as configurable starting points, not
  universal confidence guarantees. Calibrate on representative labeled traces and
  the consequences of false activation or omission.
- Prefer one owner for a workflow and narrow its trigger. Load references on demand.
  Semantic confidence is not proof of correctness or permission to execute.
- Bound state by relevance. Keep facts, inferred intent, and source provenance
  distinct; include tool receipts rather than entire logs and redact credentials.
- Measure end-to-end latency, timeouts, false positives, and missed activations for
  each decision surface. Specify budgets from the actual deployment; do not impose
  one token ratio or latency promise on every hook.
- On service failure, optional advisory features may fail open. Authorization and
  required safety checks retain their deterministic fallback; a model outage must
  not silently grant permission.

Use [Context Architect](../skills/context-architect/SKILL.md) when designing state.
The [dispatcher](../../docs/proposals/RFC-02_CORE_dynamic_skill_dispatcher.md),
[safety guardrail](../../docs/proposals/RFC-04_CORE_safety_and_tool_guardrail.md), and
[fan-out proposal](../../docs/proposals/RFC-21_EXT_speculative_fan_out.md) explain the
JEV-specific architecture. These references are read only when relevant.
