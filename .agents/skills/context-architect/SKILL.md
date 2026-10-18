---
name: context-architect
description: >
  Diagnose incorrect JEV decisions or design bounded state payloads when changing
  semantic hooks, routing, or verification in the JEV harness.
scope: project
---

# Context design

Project dependency: JEV's runtime state contracts and telemetry. Use the
[balance protocol](../../protocols/system-one-balance-protocol.md) for policy changes.

1. Inspect the failing or proposed decision: state, question, candidates, answer,
   resulting action, and observed outcome. Separate missing evidence from a model,
   code, or service error.
2. Include relevant intent and prior context, active environment, immediate causal
   history, and applicable rules/types. Omit irrelevant layers; facts and inferred
   intent remain distinct with provenance and freshness.
3. Bound inputs by the decision's actual needs. Prefer relevant hunks, symbols,
   and error receipts over whole transcripts. Redact credentials before dispatch.
   Keep sufficient source text to verify claims; avoid blind character truncation.
4. Evaluate representative traces for correct routing, false positives, missing
   context, latency, and request size. Choose budgets and thresholds for this surface
   and deployment; no universal SNR ratio, confidence minimum, or token/byte equivalence.
5. Report the payload change and measured evidence. Do not add a mandatory context
   redesign to unrelated coding tasks or assume low confidence always means starvation.
