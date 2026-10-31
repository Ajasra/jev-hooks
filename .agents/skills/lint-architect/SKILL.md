---
name: lint-architect
description: >
  Audit JEV semantic lint rules, review their decision telemetry, or author rules
  when the task targets the JEV harness and its rule configuration.
scope: project
---

# Semantic rule maintenance

Project dependencies: JEV CLI, `.agents/lint-rules/`, and decision telemetry.
See [the rule architecture](../../../docs/proposals/RFC-08_USE_CASE_semantic_code_linting.md)
for schema details and [balance policy](../../protocols/system-one-balance-protocol.md)
when changing how findings affect the agent.

1. Inspect the relevant rules, runtime schema, stack, and available telemetry.
   A telemetry-only audit reports findings without editing rules or running tests.
2. Use semantic rules for subtle architectural judgments. Leave syntax, formatting,
   secrets, and deterministic authorization/effect checks to their existing tools.
3. For an authorized rule change, define a narrow question with bounded include/exclude
   scope and useful positive/negative examples. Match the runtime's current metadata
   contract; new rules begin in observe mode.
4. Calibrate questions and thresholds using labeled violations, false positives, and
   missed violations. Defaults are starting points, not universal accuracy guarantees.
   Do not auto-promote rules based on hit count or model confidence alone.
5. Verify changed metadata/discovery and relevant behavioral checks. Use commands
   supported by the actual platform; no Windows wrapper on Linux. Avoid a full runtime
   suite for a prose-only rule clarification. Report evidence and remaining gaps.

Keep findings advisory under the current harness contract. Promotion or pruning
requires an authorized maintenance scope; it does not add a routine confirmation
step once the user has requested that work.
