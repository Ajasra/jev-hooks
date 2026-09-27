# RFC-07: Universal Output Verification & Citation Checking

> **Category**: `USE_CASE`  
> **Status**: Implemented  
> **Target Lifecycle**: `PreToolUse` (`tool.before`) & Shared Tooling (`verify_output`)  
> **Harnesses**: Google Antigravity and OpenAI Codex  
> **Implementation**: [`core/verification.py`](../src/jev/core/verification.py), [`tooling.py`](../src/jev/tooling.py), and [`services/storage.py`](../src/jev/services/storage.py)  
> **Related Protocol**: [System One Balance Protocol](../.agents/protocols/system-one-balance-protocol.md)

---

## 1. Problem

Autonomous coding agents frequently generate hallucinated interfaces and unsubstantiated claims:
1. **Invented API Signatures**: Proposing nonexistent methods or unsupported parameters that sound plausible (e.g., calling `client.auth.getTokenWithRefresh()` when only `client.get_token()` exists).
2. **Misquoted Citations & Guidelines**: Claiming a specific pattern or dependency rule is endorsed by repository documentation when the source text says the opposite.
3. **Expensive Debugging Traps**: When hallucinated code is written to disk, execution fails with runtime `AttributeError` or `TypeError`. The agent then burns 3–5 expensive turns ($0.15–$0.50 and 30–60 seconds of latency) attempting to debug an API that never existed in the first place.

Static linters and language servers only catch these issues *after* files have been mutated and dependencies resolved. Agent harnesses need a sub-100ms verification gate that evaluates proposed code against reference documentation *before* mutations land.

---

## 2. Inspiration

Operating system linkers and dynamic loaders verify symbol tables and export signatures before transferring execution control to newly loaded binaries. Similarly, modern CPU branch predictors assess instruction validity before committing speculative pipeline states.

Translating this to agent harnesses: **TypeSafe Jev acts as an automated semantic symbol and citation verifier.** In sub-100ms, non-autoregressive decision primitives evaluate whether proposed code structures are supported by reference documentation without invoking heavy generative reasoning.

---

## 3. Solution

RFC-07 establishes dual-surface verification across both Google Antigravity and OpenAI Codex:

1. **Passive `PreToolUse` Lifecycle Gate**:
   - Intercepts file mutation operations: `replace_file_content` / `write_to_file` in Antigravity, and `apply_patch` in Codex.
   - Extracts added code blocks and matches them against active Knowledge Items, docstrings, or type definitions.
   - Evaluates three parallel Jev questions in ~90ms.
   - In accordance with the [System One Balance Protocol](../.agents/protocols/system-one-balance-protocol.md), verification is **advisory and non-blocking**. Detected discrepancies inject high-signal warnings into context without denying tools or triggering confirmation fatigue.

2. **Proactive Callable Tool (`verify_output`)**:
   - Registered once in [`src/jev/tooling.py`](../src/jev/tooling.py) and exposed as a shared MCP tool.
   - Enables agents to explicitly test candidate code snippets or citations before embarking on multi-file refactors.

```mermaid
flowchart TD
    EditProposal["Proposed Edit / File Mutation<br/>(Antigravity replace / Codex apply_patch)"] --> Extract["Diff Normalization<br/>(Extract added lines & imports)"]
    RefDocs["Reference Context<br/>(Active KIs, docstrings, SDK stubs)"] --> Verifier["Jev Verifier Core (~90ms)"]
    Extract --> Verifier

    subgraph JevBatch ["Parallel TypeSafe Primitives"]
        Q1["method_supported_by_docs (Noul)"]
        Q2["arguments_match_spec (Noul)"]
        Q3["support_level (Choice: fully_supported | extrapolated | contradicted)"]
    end
    Verifier --> JevBatch

    JevBatch --> Evaluate{"Supported?"}
    Evaluate -->|Pass (Noul >= 0.70)| Pass["Execute Tool Unhindered"]
    Evaluate -->|Discrepancy (Noul < 0.40 or contradicted)| Advisory["Inject Advisory Context<br/>Antigravity: Prompt Context<br/>Codex: hookSpecificOutput.additionalContext"]
    Advisory --> Pass
```

---

## 4. Concrete Example & Impact

### Before: Hallucination Cascade
1. Agent plans: *"I will refresh authentication using `client.refreshTokenWithScope('repo')`."*
2. Agent calls `replace_file_content` on `src/auth.py`.
3. Agent executes tests: `TypeError: refreshTokenWithScope() got unexpected keyword argument 'scope'`.
4. Agent spends 3 subsequent turns reading files, searching web, and attempting alternative bad signatures.
5. **Cost**: 4 turns, 38,000 tokens, 45 seconds elapsed.

### After: RFC-07 Sub-100ms Advisory
1. Agent proposes `replace_file_content` with `client.refreshTokenWithScope('repo')`.
2. `PreToolUse` verification runs in 84ms.
3. Jev reports:
   - `method_supported_by_docs`: `0.18`
   - `support_level`: `contradicted`
4. Harness injects advisory notice into the agent context:
   > `[Jev Verification Advisory] Proposed call 'refreshTokenWithScope' is not supported by auth client documentation. Documented signature is 'client.refresh_token()'.`
5. Agent self-corrects on Turn 1 before writing invalid code to disk.
6. **Impact**: Zero failed test turns, $0.35 saved per intercepted hallucination, zero developer friction.

---

## 5. Technical Specification & Implementation

### A. Jev Decision Primitives

Verification evaluates state composed of the proposed code snippet and reference documentation against three questions:

```json
{
  "method_supported_by_docs": {
    "type": "noul",
    "instructions": "Does the reference documentation or type definition confirm that the proposed function, method, or API symbol exists and is valid?"
  },
  "arguments_match_spec": {
    "type": "noul",
    "instructions": "Are the arguments and parameters passed in the code snippet compatible with the documented parameter names and types?"
  },
  "support_level": {
    "type": "choice",
    "instructions": "How strongly does the source document support the code or claim being made?",
    "criteria": {
      "fully_supported": "The document explicitly documents this exact API, method signature, or claim.",
      "extrapolated": "The document mentions related concepts but not this specific method signature.",
      "contradicted": "The document explicitly specifies a different signature, deprecation, or prohibition."
    }
  }
}
```

### B. Diff & Hunk Normalization Across Harnesses

The extraction layer normalizes incoming operations into clean candidate code:
- **Google Antigravity**: Extracts `arguments.get("ReplacementContent")` or `arguments.get("CodeContent")`.
- **OpenAI Codex**: Parses unified patch hunks from `arguments.get("command")` or `arguments.get("patch")`, isolating lines prefixed with `+` (excluding file headers).

### C. Harness IPC Contracts

#### Antigravity (`PreToolUse`)
Emits a non-blocking `ContextItem` merged into the turn prompt:
```json
{
  "text": "[Jev Verification Advisory] Method 'refreshTokenWithScope' appears contradicted by reference docs (confidence: 0.82). Check exports before proceeding.",
  "source": "verification"
}
```

#### Codex (`PreToolUse`)
Emits `additionalContext` in `hookSpecificOutput` without setting `permissionDecision: deny`:
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "additionalContext": "[Jev Verification Advisory] Method 'refreshTokenWithScope' appears contradicted by reference docs (confidence: 0.82)."
  }
}
```

### D. SQLite Decision Logging

Auditable logs are recorded in `verification_decisions`:
- `session_id`, `harness`, `target_path`
- `method_supported` (`float`), `args_match` (`float`), `support_level` (`str`)
- `advisory_emitted` (`bool`), `duration_ms` (`float`), `created_at` (`str`)

### E. Shared Callable Tool (`verify_output`)

Registered in [`src/jev/registry.py`](../src/jev/registry.py) and [`src/jev/tooling.py`](../src/jev/tooling.py):
- **Inputs**: `code_snippet` (str), `reference_context` (str)
- **Output**:
  ```json
  {
    "verified": true,
    "method_supported": 0.94,
    "arguments_match": 0.89,
    "support_level": "fully_supported",
    "advisory": null,
    "duration_ms": 78.5
  }
  ```
