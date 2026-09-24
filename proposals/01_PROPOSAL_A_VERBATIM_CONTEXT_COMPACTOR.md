# Proposal A: Verbatim Transcript Compactor for Antigravity

## 1. Problem Statement

Long-running agent workflows (e.g., refactoring large codebases, running `/goal` tasks, iterative test/fix cycles) generate immense conversation transcripts. 

Traditional context management approaches exhibit critical flaws:
1. **Sliding Window Truncation**: Older turns drop off entirely, losing original requirements, user constraints, and architectural plans established at the start.
2. **Generative LLM Summarization**:
   - **Lossy**: Specific compiler flags, line numbers, file paths, and exact error outputs are eliminated or smudged.
   - **Hallucinations**: Summaries often misrepresent what changes were committed or tested.
   - **High Latency & Token Burn**: Running an LLM over a 50k–100k token history takes 10–30 seconds and thousands of tokens per compaction step.

---

## 2. Core Idea: Fast Selective Tool Pruning with Jev

Adapted from [tamaratran/fast-jev-compaction](https://github.com/tamaratran/fast-jev-compaction), this proposal implements **zero-rewrite verbatim compaction**:
- User prompts and assistant reasoning/discourse are **never summarized or altered**.
- Only historical tool calls and tool outputs are scored and surgically pruned.
- Decisions are made by Jev evaluating dual `Noul` questions per tool call against the entire conversation state in 1–2 concurrent requests.

```mermaid
flowchart TD
    RawHistory["Full Transcript (Messages + Tool Calls)"] --> PinFilter["Pin Boundary:<br/>- First user prompt & plan<br/>- Last N recent turns (e.g. 6 turns)"]
    
    PinFilter --> CandidateCalls["Historical Candidate Tool Calls<br/>(e.g., view_file, grep_search, run_command)"]
    
    CandidateCalls --> StatePrep["Prepare Jev State:<br/>Full conversation with tool outputs masked to<br/>'ok, 4120 chars (omitted)'"]
    
    StatePrep --> JevBatch["Dispatch Parallel Noul Questions to Jev"]
    
    subgraph JevQuestions ["Per-Call Jev Evaluation"]
        N1["call_{id}: Does knowing this call was made still matter?"]
        N2["result_{id}: Is the verbatim output still needed?"]
    end
    
    JevBatch --> JevQuestions
    JevQuestions --> PruneLogic{"Compare against keepThreshold (0.5)"}
    
    PruneLogic -->|keepResult ≥ 0.5| KeepFull["Keep Tool Call + Complete Output"]
    PruneLogic -->|keepCall ≥ 0.5| KeepStub["Keep Call Metadata + Truncate Output to 300ch stub"]
    PruneLogic -->|Both < 0.5| DropAll["Prune Call and Result Entirely"]
    
    KeepFull --> ReconstructedHistory["Compact History (100% Verbatim Prose)"]
    KeepStub --> ReconstructedHistory
    DropAll --> ReconstructedHistory
```

---

## 3. Tool-Specific Pruning Dynamics in Antigravity

Antigravity uses specific tools that benefit directly from this tri-state decision matrix:

| Tool Type | Example Scenario | Typical Jev Decision | Action Taken |
| :--- | :--- | :--- | :--- |
| `view_file` | Read a file 15 turns ago that was later modified by `replace_file_content` | `keepCall`: 0.6<br/>`keepResult`: 0.1 | Keep `view_file` path to show it was inspected, drop the 40KB file contents. |
| `grep_search` | Search pattern returned 50 lines of vendor code, followed by refined search | `keepCall`: 0.2<br/>`keepResult`: 0.05 | Both < 0.5: Erase entire exploratory failure to clean context. |
| `run_command` | Build command failed with 200 lines of stack traces, then fixed in next step | `keepCall`: 0.7<br/>`keepResult`: 0.2 | Truncate result to first 300 chars + error code stub. |
| `run_command` | Test command currently failing that the agent is trying to fix | `keepCall`: 0.95<br/>`keepResult`: 0.92 | Keep full verbatim stack trace; do not truncate. |
| `browser_subagent` | Subagent returned raw DOM or long trace log | `keepCall`: 0.8<br/>`keepResult`: 0.3 | Retain task summary; drop intermediate DOM dumps. |

---

## 4. Antigravity Implementation Architecture

### 4.1 State Masking
Before presenting the transcript to Jev, all tool outputs are masked to short metadata strings:
```typescript
interface MaskedToolResult {
  tool_use_id: string;
  summary: string; // e.g. "ok, 12,450 characters (omitted)"
}
```
This fits 40–80 turns of conversation into Jev's default 25,000 token state budget without losing conversational context.

### 4.2 Batching Dual Nouls
For every non-pinned tool call $i$, generate:
```typescript
const questions = {
  [`call_${call.id}`]: {
    type: 'noul',
    instructions: `Tool call ${call.id} (${call.tool} on ${call.target}) should stay in history: knowing this action was taken still matters for upcoming steps.`
  },
  [`result_${call.id}`]: {
    type: 'noul',
    instructions: `The full output of tool call ${call.id} (${call.resultChars} chars) should stay in history verbatim: the agent still needs exact lines/content and re-running would not suffice.`
  }
};
```

### 4.3 Clean History Rebuilding
- Untouched messages remain references to their original objects (no mutation).
- Empty messages (where all tool calls and results were dropped and no text remains) are filtered out cleanly.
- No dangling tool results are ever left without their matching tool calls.

---

## 5. Expected Benefits

1. **Zero Information Distortion**: Critical constraints, paths, and commands never get rewritten or lost.
2. **Speed**: Evaluated in ~150–300ms across dozens of tool calls (compared to 15–30s with a generative LLM).
3. **Massive Token Reduction**: Typically achieves **60% to 85% token reduction** on tool-heavy transcripts without losing a single character of human or agent reasoning.
