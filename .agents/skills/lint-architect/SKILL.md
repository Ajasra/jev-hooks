---
name: lint-architect
description: >
  Audits existing semantic lint rules, evaluates telemetry for rule promotion, and authors project-specific rules aligned with RFC-08 and System One balance.
  Use when asked to review semantic rules, inspect lint accuracy, or add new architectural rules tailored to a repository's stack.
concerns: [system-one-balance]
---

# Lint Architect Protocol

The Lint Architect manages project-specific semantic lint rules in [`.agents/lint-rules/`](../../lint-rules/). It complements [RFC-08: Semantic Code Linting](../../../proposals/RFC-08_USE_CASE_semantic_code_linting.md) by ensuring rules stay lean, high-leverage, non-redundant, and non-blocking.

---

## Phase 0: Setup and Protocols
1. Review referenced protocols:
   - [System One Balance Protocol](../../protocols/system-one-balance-protocol.md)
   - [RFC-08: Semantic Code Linting](../../../proposals/RFC-08_USE_CASE_semantic_code_linting.md)
2. Ensure working rules follow the Knowledge Item directory layout:
   ```text
   .agents/lint-rules/<rule-id>/
     metadata.json
     artifacts/
       policy.md
   ```

---

## Phase 1: Ingest and Check
1. Determine the task mode:
   - **Audit**: Review existing rules in `.agents/lint-rules/` for redundancy, threshold validity, and domain boundaries.
   - **Calibrate / Review Telemetry**: Run `python -m jev.cli lint-stats` to evaluate false-positive rates and hit counts.
   - **Author New Rule**: Discover repository tech stack (e.g., Python, TypeScript, Go) and formulate a targeted architectural invariant question.
2. Invariant Guardrails against Competition & Overlap:
   - **DO NOT duplicate static linters**: Never create rules for syntax, formatting, imports, or secret regexes already owned by AST/static tooling (`ruff`, `tsc`, `gitleaks`, `trufflehog`).
   - **DO NOT duplicate deterministic safety**: Never create rules duplicating invariant shell bans (`rm -rf`, `DROP TABLE`).
   - **Narrow Scope Only**: Focus strictly on subtle architectural boundaries, layering violations, or harness abstraction leaks.

---

## Phase 2: Processing

### Mode A: Authoring New Rules
1. Discover project framework and architectural patterns by inspecting `pyproject.toml`, `package.json`, or directory tree.
2. Formulate a single, crisp polar question for TypeSafe Noul evaluation.
3. Define tightly bounded `include` and `exclude` glob patterns so unaffected files bypass evaluation at 0ms cost.
4. Author `metadata.json`:
   - `id`: Lowercase snake_case prefixed with `lr_` (e.g., `lr_boundary_check`).
   - `version`: Starts at `1`.
   - `status`: `"active"`.
   - `mode`: **MUST ALWAYS start in `"observe"`**.
   - `level`: `"warning"` or `"error"`.
   - `review_threshold`: Default `0.60`.
   - `violation_threshold`: Default `0.82` ($0 \le \text{review} \le \text{violation} \le 1$).
5. Author `artifacts/policy.md` detailing the architectural rationale and positive/negative examples.

### Mode B: Telemetry Audit and Calibration
1. Query SQLite decision telemetry:
   ```cmd
   cmd /c python -m jev.cli lint-stats
   ```
2. For each rule:
   - Inspect total evaluations, confirmed violations, and false positives.
   - If false positives $> 10\%$, adjust the question phrasing or narrow the glob patterns.
   - If a rule in `observe` mode has consistent confirmed accuracy across real diffs, propose a manual Git change to `"mode": "advisory"`.
   - **Never rewrite or promote rules automatically**.

### Mode C: Catalog Pruning
1. Scan for rules that have become redundant due to new deterministic tooling or obsolete frameworks.
2. Remove obsolete rule directories or set `"status": "deprecated"`.

---

## Phase 3: The System One Balance Pass
- Confirm that semantic findings remain advisory:
  - Antigravity uses `presentation: prompt_user` (developer inquiry, no tool locks).
  - Codex uses `presentation: warn_user` (informational warning).
- Confirm that new rules are created in `mode: "observe"`.
- Confirm that no rule introduces imperative tool bans (`DO NOT CALL TOOLS`).

---

## Phase 4: Output Execution & Verification
1. Validate rule discovery and JSON formatting:
   ```cmd
   cmd /c python -m jev.cli lint --harness antigravity
   ```
2. Verify test suite passes without regressions:
   ```cmd
   cmd /c pytest tests/test_semantic_lint.py
   ```
