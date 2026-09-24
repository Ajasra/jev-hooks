# Jev (TypeSafe AI) Integration for Google Antigravity

Machine-native **System One** semantic control layer for Google Antigravity, implementing automated skill routing, execution safety guardrails, real-time log pruning, and verbatim context compaction using **TypeSafe AI's Jev model**.

---

## Architecture Overview

Language model harnesses traditionally rely on monolithic autoregressive models (System Two) for both high-level reasoning and low-level control flow. In long-horizon agent workflows, this causes context rot, high token cost, and lossy summarization.

This repository integrates **TypeSafe Jev** (a non-autoregressive, calibrated decision model) into the **Google Antigravity** harness:
- **Deterministic Code**: Manages sandboxed filesystems, loops, and baseline security rules.
- **System One (Jev)**: Evaluates high-frequency semantic micro-decisions (skill relevance, tool safety, log compaction) in ~70–200ms at $0.042/1M input tokens (unmetered free outputs).
- **System Two (Gemini)**: Focuses computational capacity on long-horizon planning, system architecture, and code synthesis, operating over clean, verbatim context.

```mermaid
flowchart TD
    UserPrompt["Developer Instruction"] --> Hook_PreInv["PreInvocation Hook<br/>(.agents/hooks/jev_skill_router.py)"]
    Hook_PreInv -->|Injects Only Qualifying Skills| LLM_Turn["Gemini Foundation Model<br/>(Generates Code / Plans / Tool Calls)"]
    LLM_Turn -->|Proposed Action| Hook_PreTool["PreToolUse Hook<br/>(.agents/hooks/jev_safety_gate.py)"]
    Hook_PreTool -->|Blast Radius Score ≤ 1.0| Tool_Exec["Local OS / Tool Execution<br/>(cmd /c, file edits)"]
    Hook_PreTool -->|Risk Score ≥ 3.0| HumanModal["Prompt User Confirmation (ask_question)"]
    HumanModal -->|Approved| Tool_Exec
    Tool_Exec -->|Raw Stdout / Stderr| Hook_PostTool["PostToolUse Hook<br/>(.agents/hooks/jev_output_pruner.py)"]
    Hook_PostTool -->|Pruned / Sanitized Receipt| Storage["Trajectory Storage<br/>(storage/sessions/traj-*)"]
    Storage --> GC_Trigger{"Context > 60% Capacity?"}
    GC_Trigger -->|Yes| Jev_GC["Trajectory GC Sweep<br/>(jev_compactor.py)"]
    Jev_GC -->|Verbatim Cleaned History| Storage
    GC_Trigger -->|No| NextTurn["Proceed to Next Turn"]
```

---

## Quick Start & Configuration

### 1. Environment Configuration (`.env`)
The hook scripts include a zero-dependency environment loader that automatically looks for `.env` files in:
1. `.agents/.env` (recommended for agent-scoped config)
2. `.env` (project root)
3. System environment variables

Copy the example template:
```cmd
cmd /c copy .agents\.env.example .agents\.env
```

Edit `.agents/.env`:
```ini
# TypeSafe AI / Jev Configuration
# Get your API key at: https://console.typesafe.ai/keys
TYPESAFE_API_KEY=your_typesafe_api_key_here
TYPESAFE_ENDPOINT=https://api.typesafe.ai/v1/systemone
JEV_MODEL=jev-latest

# Optional Parameters
JEV_HOOK_TIMEOUT_SECONDS=0.8
JEV_KEEP_THRESHOLD=0.50
JEV_PRESERVE_RECENT_MESSAGES=6
```

> **Note**: If `TYPESAFE_API_KEY` is not set, all hooks safely fail open (transparently passing prompts, commands, and logs unhindered).

---

## Implemented Lifecycle Hooks

All hooks are wired declaratively in [`.agents/hooks.json`](file:///d:/01_GIT/Jev/.agents/hooks.json):

```json
{
  "enabled": true,
  "PreInvocation": [
    {
      "command": "cmd /c python .agents/hooks/jev_skill_router.py"
    }
  ],
  "PreToolUse": [
    {
      "matcher": "run_command|write_to_file|replace_file_content",
      "command": "cmd /c python .agents/hooks/jev_safety_gate.py"
    }
  ],
  "PostToolUse": [
    {
      "matcher": "run_command|grep_search|view_file",
      "command": "cmd /c python .agents/hooks/jev_output_pruner.py"
    }
  ]
}
```

---

### 1. PreInvocation: Dynamic Skill Routing (`jev_skill_router.py`)
- **Location**: [`.agents/hooks/jev_skill_router.py`](file:///d:/01_GIT/Jev/.agents/hooks/jev_skill_router.py)
- **Problem**: Advertising 50+ installed skills in system prompts wastes 5k–20k tokens per turn and causes skill hallucinations.
- **Solution**: Evaluates the incoming user prompt against all `SKILL.md` frontmatter descriptions in ~100ms.
- **Behavior**:
  - Asks Jev `requires_skill` (Noul) and `selected_skill` (Choice).
  - If $P \ge 0.65$ and confidence $C \ge 0.70$, outputs an `ephemeralMessage` hydrating only the winning skill's instructions.
  - If no skill fits, passes zero extra tokens to the LLM.

#### Test Manually:
```cmd
cmd /c python -c "import json; print(json.dumps({'prompt': 'Check repository for over-engineering and unused dependencies'}))" | python .agents/hooks/jev_skill_router.py
```

---

### 2. PreToolUse: Command Safety Gate (`jev_safety_gate.py`)
- **Location**: [`.agents/hooks/jev_safety_gate.py`](file:///d:/01_GIT/Jev/.agents/hooks/jev_safety_gate.py)
- **Problem**: Autonomous agents can accidentally run destructive shell commands (`rm -rf`, `git reset --hard`, accidental directory format).
- **Solution**:
  - Deterministic Windows check: Enforces `cmd /c` prefix on shell commands.
  - Semantic Blast Radius check: Jev scores commands on an ordered 0–3 risk rubric:
    - Level 0: Read-only inspection (e.g. `dir`, `git status`).
    - Level 1: Idempotent local mutation (e.g. `git checkout -b`).
    - Level 2: Non-idempotent mutation or network calls.
    - Level 3: Destructive operations (recursive deletion, credential access).
- **Behavior**:
  - If blast radius $\ge 2$ or `is_destructive` $\ge 0.70$, exits with status code `1`, halting execution and prompting developer confirmation.

#### Test Manually:
```cmd
cmd /c python -c "import json; print(json.dumps({'tool_name': 'run_command', 'args': {'CommandLine': 'cmd /c del /f /s /q build'}}))" | python .agents/hooks/jev_safety_gate.py
```

---

### 3. PostToolUse: Real-Time Stream Pruner (`jev_output_pruner.py`)
- **Location**: [`.agents/hooks/jev_output_pruner.py`](file:///d:/01_GIT/Jev/.agents/hooks/jev_output_pruner.py)
- **Problem**: Passing massive test suites, build outputs, or grep searches (2,000+ lines) directly into conversation history rapidly exhausts context windows.
- **Solution**:
  - Intercepts completed tool stdout exceeding 1,000 characters.
  - Asks Jev whether the execution succeeded cleanly and whether any error stack traces exist.
  - If clean, compresses the output into a concise structural receipt (e.g. `[... Jev Stream Pruner: Execution succeeded cleanly. 12,410 non-failing log characters omitted ...]`).
  - If failures or stack traces exist, leaves the output completely intact for agent debugging.

#### Test Manually:
```cmd
cmd /c python -c "import json; print(json.dumps({'exit_code': 0, 'stdout': 'test passed\n' * 500}))" | python .agents/hooks/jev_output_pruner.py
```

---

### 4. Trajectory Garbage Collector (`jev_compactor.py`)
- **Location**: [`.agents/hooks/jev_compactor.py`](file:///d:/01_GIT/Jev/.agents/hooks/jev_compactor.py)
- **Problem**: Traditional LLM summarization forgets exact compiler flags, line numbers, and file paths (the "Funes Trap").
- **Solution**: Adapts Tamara Tran's `fast-jev-compaction` algorithm to Antigravity session trajectories:
  - Pins root prompt (`messages[0]`) and recent turns (`preserveRecentMessages=6`).
  - Evaluates dual Nouls per tool call:
    - $Q_1$: Does knowing this call was made still matter?
    - $Q_2$: Does the full output need to stay verbatim, or is it stale?
  - Drops obsolete calls, truncates superseded results to 300ch stubs, and preserves all user prompts and code diffs **100% verbatim**.

#### Run on a Trajectory File:
```cmd
cmd /c python .agents/hooks/jev_compactor.py "path/to/trajectory.json"
```

---

## Proposals & Architectural Specifications

The [proposals/](file:///d:/01_GIT/Jev/proposals) directory contains complete research and technical blueprints:

| Document | Description |
| :--- | :--- |
| **[proposals/README.md](file:///d:/01_GIT/Jev/proposals/README.md)** | Master proposals index & architecture flowchart. |
| **[18_ARCHITECTURAL_TREATISE_SYSTEM_ONE_ANTIGRAVITY.md](file:///d:/01_GIT/Jev/proposals/18_ARCHITECTURAL_TREATISE_SYSTEM_ONE_ANTIGRAVITY.md)** | Master treatise: *Machine-Native Semantic Control in Google Antigravity*. |
| **[01_PROPOSAL_A_VERBATIM_CONTEXT_COMPACTOR.md](file:///d:/01_GIT/Jev/proposals/01_PROPOSAL_A_VERBATIM_CONTEXT_COMPACTOR.md)** | Verbatim Transcript Compactor blueprint. |
| **[02_PROPOSAL_B_DYNAMIC_SKILL_DISPATCHER.md](file:///d:/01_GIT/Jev/proposals/02_PROPOSAL_B_DYNAMIC_SKILL_DISPATCHER.md)** | Two-stage progressive skill selection & disclosure. |
| **[03_PROPOSAL_C_KNOWLEDGE_ITEM_MATCHER.md](file:///d:/01_GIT/Jev/proposals/03_PROPOSAL_C_KNOWLEDGE_ITEM_MATCHER.md)** | Automated repository Knowledge Item memory pre-filter. |
| **[04_PROPOSAL_D_SAFETY_AND_TOOL_ROUTER.md](file:///d:/01_GIT/Jev/proposals/04_PROPOSAL_D_SAFETY_AND_TOOL_ROUTER.md)** | Pre-execution safety guardrail & closed-set tool routing. |
| **[06_USE_CASE_MODEL_ROUTING.md](file:///d:/01_GIT/Jev/proposals/06_USE_CASE_MODEL_ROUTING.md)** | 70ms task difficulty scoring to tier between Flash and Pro models. |
| **[07_USE_CASE_OUTPUT_AND_CITATION_VERIFICATION.md](file:///d:/01_GIT/Jev/proposals/07_USE_CASE_OUTPUT_AND_CITATION_VERIFICATION.md)** | Pre-execution verification of generated API signatures against docs. |
| **[08_USE_CASE_SEMANTIC_CODE_LINTING.md](file:///d:/01_GIT/Jev/proposals/08_USE_CASE_SEMANTIC_CODE_LINTING.md)** | Automated CI/CD PR diff checking against architectural guidelines. |
| **[09_USE_CASE_STRUCTURED_DATA_EXTRACTION_CASCADE.md](file:///d:/01_GIT/Jev/proposals/09_USE_CASE_STRUCTURED_DATA_EXTRACTION_CASCADE.md)** | Regex extraction + Jev Choice for schema-guaranteed data extraction. |
| **[10_USE_CASE_RAG_RERANKING_AND_FILTERING.md](file:///d:/01_GIT/Jev/proposals/10_USE_CASE_RAG_RERANKING_AND_FILTERING.md)** | Parallel vector chunk re-ranking, pruning 85% of distractor noise. |
| **[11_USE_CASE_LINE_BY_LINE_SEMANTIC_SEARCH.md](file:///d:/01_GIT/Jev/proposals/11_USE_CASE_LINE_BY_LINE_SEMANTIC_SEARCH.md)** | Scoring hundreds of line IDs to locate exact clauses in massive files. |
| **[12_USE_CASE_REALTIME_GUARDRAILS.md](file:///d:/01_GIT/Jev/proposals/12_USE_CASE_REALTIME_GUARDRAILS.md)** | Sub-100ms scans for prompt injections and secret/credential leaks. |
| **[13_USE_CASE_AUTONOMOUS_UI_NAVIGATION.md](file:///d:/01_GIT/Jev/proposals/13_USE_CASE_AUTONOMOUS_UI_NAVIGATION.md)** | Sub-100ms DOM element selection for browser automation. |
| **[14_USE_CASE_KNOWLEDGE_GRAPH_ENTITY_ALIGNMENT.md](file:///d:/01_GIT/Jev/proposals/14_USE_CASE_KNOWLEDGE_GRAPH_ENTITY_ALIGNMENT.md)** | High-throughput entity deduplication across inconsistent databases. |
| **[15_USE_CASE_PREDICTIVE_ML_FEATURE_EXTRACTION.md](file:///d:/01_GIT/Jev/proposals/15_USE_CASE_PREDICTIVE_ML_FEATURE_EXTRACTION.md)** | Continuous calibrated numeric features for CatBoost / XGBoost. |
| **[16_INSPIRATION_SHAPESHIFT_DYNAMIC_UI.md](file:///d:/01_GIT/Jev/proposals/16_INSPIRATION_SHAPESHIFT_DYNAMIC_UI.md)** | Shapeshift Case Study: *"Jev decides, code computes"*. |
| **[17_FRAMEWORK_PYDANTIC_AI_TYPESAFE_INTEGRATION.md](file:///d:/01_GIT/Jev/proposals/17_FRAMEWORK_PYDANTIC_AI_TYPESAFE_INTEGRATION.md)** | Reference implementation: Pydantic AI's native `TypeSafeModel`. |

---

## Defensive Engineering & Failure Policy

1. **Strict Timeout**: All hook scripts configure an **800ms HTTP timeout**. If the network stalls, the script exits cleanly without blocking Antigravity.
2. **Fail-Open Policy**: If Jev is unreachable or encounters an error:
   - Skills fall back to standard baseline indexing.
   - Logs are preserved unedited.
   - The agent continues uninterrupted.
3. **Fail-Closed on Severe Mutation**: High-risk shell commands (`del /f /s /q`, `rm -rf`) require developer confirmation if Jev flags risk.
