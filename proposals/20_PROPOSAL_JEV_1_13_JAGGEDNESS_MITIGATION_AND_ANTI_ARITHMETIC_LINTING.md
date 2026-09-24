# Proposal 20: Jev 1.13 Jaggedness Mitigation & Anti-Arithmetic Architectural Guardrails

## 1. Context & Motivation

On September 17, 2026, TypeSafe AI published its official [Model Jaggedness Guide for Jev 1.13](https://docs.typesafe.ai/model-jaggedness/jev-1.13.md).

While `jev-1.13` is extraordinarily fast (~70–200ms) and provides calibrated common-sense judgments at $0.042/1MTok, it is explicitly **not** an autoregressive generalist LLM, a calculator, or a calendar engine. Attempting to use Jev for arithmetic, character counting, or multi-hop temporal logic leads to degraded calibration and brittle integrations.

This proposal establishes a set of **runtime linters and architectural design rules** within the Antigravity integration layer to permanently prevent known `jev-1.13` failure modes.

---

## 2. The 9 Known Jagged Edges of `jev-1.13`

The official documentation identifies 9 distinct failure modes:

| # | Known Failure Mode | Underlying Root Cause | Architectural Mitigation in Antigravity |
| :--- | :--- | :--- | :--- |
| **1** | **Literal Reading** | Jev evaluates verbatim words, not implied developer intent. | Specify explicit conditions in `instructions` and define edge-case rubrics in `criteria`. |
| **2** | **Math & Counting** | Non-autoregressive architecture lacks token counting and numeric arithmetic. | **Rule 1: Keep math in code.** Never ask Jev to tally occurrences or calculate totals. |
| **3** | **Date & Time Comparison** | Jev reads dates as semantic strings, not chronological timestamps. | **Rule 2: Split extraction and comparison.** Extract parts via `Choice`, perform chronology in Python. |
| **4** | **Multi-Hop Indirection** | Double negatives and nested properties degrade judgment calibration. | Point questions directly to named JSON paths (e.g. `state.user.id`). |
| **5** | **Bloated Distractor State** | Sending huge raw dumps dilutes attention across irrelevant text. | Pre-filter context in code; prune logs via `jev_output_pruner.py` before sending. |
| **6** | **Adversarial Content** | State text containing prompt injection can bias unconstrained questions. | Anchor decisions to rigid criteria enums; enforce thresholding in Python. |
| **7** | **Contradictory Instructions** | Contradicting instructions and criteria (e.g. true=no) confuse inference. | Static AST linter checks semantic polarity alignment in question definitions. |
| **8** | **Structural Invariants** | $P(\text{noul})$ and $1 - P(\text{not noul})$ are not mathematically coupled. | Use `Choice` for relative selection among candidates; use `Noul` for absolute gating. |
| **9** | **Prose Generation** | Forcing Jev to generate strings via chained choices is slow and fragile. | Hand off prose generation exclusively to Gemini/Claude (System 2). |

---

## 3. High-Impact Anti-Patterns & Corrected Implementations

### 3.1 Anti-Pattern: Asking Jev to Count Errors in Logs
```python
# ❌ INCORRECT (Jev will miscount):
questions = {
    "error_count": Score(
        instructions="Count how many times 'AssertionError' appears in the log.",
        criteria=["0", "1-3", "4-10", "More than 10"]
    )
}
```

```python
# ✅ CORRECT (Code counts, Jev judges semantic severity):
raw_count = stdout.count("AssertionError")

if raw_count > 0:
    questions = {
        "severity": Score(
            instructions="Given these failure snippets, rate the regression severity.",
            criteria=[
                "Cosmetic / flaky timing issue",
                "Isolated functional regression with clear fix",
                "Catastrophic build failure or data corruption risk"
            ]
        )
    }
```

---

### 3.2 Anti-Pattern: Date Chronology Comparison
```python
# ❌ INCORRECT (Jev cannot reliably compare mixed-format dates):
questions = {
    "is_expired": Noul(
        instructions="Did the security certificate expire before the webhook payload was sent?"
    )
}
```

```python
# ✅ CORRECT (Extract components with Choice, compare in Python):
# Date components are closed sets (12 months, 31 days). 
# Code parses and runs datetime.now() > cert_date.
```

---

### 3.3 High-Cardinality Partitioning (Max 255 Options)
The official TypeSafe API imposes a hard limit of **255 options per `Choice` question**.

When cataloging hundreds of tools, files, or symbols (e.g., Nous Hermes 182-skill catalog or workspace symbol trees with 1,000+ entries), Antigravity must execute a **2-stage hierarchical cascade**:
1. **Stage 1**: Partition candidates into domain clusters (max 10 categories). Jev selects the winning cluster.
2. **Stage 2**: Send candidate items within the winning cluster (max 50 options). Jev selects the specific item.

---

## 4. Antigravity Static Hook Linter

To automate these rules, this proposal includes an automated check inside [`.agents/hooks/jev_skill_router.py`](file:///d:/01_GIT/Jev/.agents/hooks/jev_skill_router.py) and CI linting:
- **`check_no_math_in_instructions()`**: Flags regex matches for "how many", "count", "sum", "total" in Jev payloads.
- **`check_cardinality_limit()`**: Asserts `len(criteria) <= 255` on all `Choice` questions.
- **`check_score_criteria_type()`**: Ensures `criteria` for `Score` questions is an ordered list (2–10 items) rather than a dictionary or freeform string.
