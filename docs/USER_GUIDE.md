# Jev for Antigravity: User Guide & Operational Manual

> **Audience**: Application Developers & Workspace Operators  
> **Status**: Active Production Standard  
> **Target Harness**: Google Antigravity 2.0  

---

## 1. Problem: The Fragility of Generative Agents

Autonomous coding harnesses give generative models (Gemini, Claude, GPT) direct local execution privileges: running terminal commands, editing source trees, and executing test suites.

However, relying exclusively on large generative models for low-level execution creates constant friction:
* **Accidental Destructive Execution**: An innocent request like *"clean up old benchmarks"* can cause an agent to emit `cmd /c rmdir /s /q benchmarks` or `git reset --hard` before you can react.
* **Severe Token Bloat**: Loading 50+ domain skills into the prompt consumes 5,000–25,000 tokens on *every single turn*, slowing down responses and driving up costs.
* **Lossy Context Summaries**: When sessions grow long, generative summarization wipes out line numbers, compiler error codes, and verbatim user constraints.

---

## 2. Inspiration: Reflexes & Muscle Memory

In human biology, routine survival actions (pulling your hand from a hot stove or catching a falling glass) do not consult the conscious cerebral cortex. They are handled by sub-conscious, high-speed **reflex arcs** in milliseconds.

Similarly, an AI coding harness should not ponder for 5 seconds using an expensive LLM whether `git status` is safe or which skill to activate. Low-level control flow belongs in a dedicated, high-speed **System One reflex layer**.

---

## 3. Solution: Jev Machine-Native Hooks

**Jev** is TypeSafe AI's non-autoregressive System One decision model:
* **Sub-120ms Latency**: 190x faster than LLMs, executing in parallel before the primary model even starts generation.
* **Extreme Cost Efficiency**: **$0.042 per 1M tokens** with free unmetered outputs.
* **Mathematical Guaranteed Typing**: Native `Choice`, `Score`, and `Noul` primitives with zero schema validation failures.

When integrated into Antigravity, Jev operates seamlessly in the background:
1. **Intercepts destructive actions** before shell execution and presents an interactive IDE confirmation modal.
2. **Dynamically activates relevant skills** on the fly, keeping system prompts lean.
3. **Speculatively prefetches git diffs and test failures** at Turn 1, eliminating wasted exploratory turns.
4. **Prunes repetitive build logs** to 300-char receipts while preserving 100% of user discourse and code edits verbatim.

---

## 4. Visual Walkthrough & Examples

### A. The Safety Gate Intercept Modal
When an agent attempts a destructive command (`rmdir /s`, `git reset --hard`, or unverified script deletion), Jev halts execution instantly:

![Jev Safety Gate Intercept Modal](../proposals/assets/jev_safety_gate_intercept_modal.png)

You can choose:
* **Allow Once**: Authorize this specific execution.
* **Save for Session**: Authorize this pattern for the rest of this conversation.
* **Save Always**: Save a permanent rule to SQLite so you are never asked again.
* **Cancel**: Abort the tool call safely.

### B. Dynamic Skill Activation Badge
When your prompt requires a specific domain skill, Jev activates it ephemerally and displays an in-chat badge:

```text
> **Activated Skill**: `app-security`
```

### C. Speculative Pre-Flight Badge
Before primary reasoning starts, Jev speculatively evaluates the context and prefetches diffs or test logs into Turn 1:

![Jev Speculative Pre-Flight Badge](../proposals/assets/jev_speculative_preflight_badge.png)

```text
> **Jev Speculative Pre-Flight**: Attached speculative evidence (git_prefetch (P=0.77) in 266ms).
```

---

## 5. Getting Started (60 Seconds)

### Step 1: Configure Your API Key
Copy the template environment file:
```cmd
cmd /c copy .agents\.env.example .agents\.env
```

Open `.agents/.env` and supply your key:

#### Option A: OpenRouter (Recommended)
```ini
OPENROUTER_API_KEY=sk-or-v1-your_openrouter_api_key_here
```

#### Option B: Direct TypeSafe AI
```ini
TYPESAFE_API_KEY=your_typesafe_key_here
TYPESAFE_ENDPOINT=https://api.typesafe.ai/v1/systemone
JEV_MODEL=jev-latest
```

### Step 2: Verify Connectivity
Run the self-diagnostic test:
```cmd
cmd /c python test_jev.py
```
Expected output:
```text
[*] API Key detected: sk-or-v1-...
[*] Endpoint: https://openrouter.ai/api/v1/systemone
[*] Model: typesafe/jev-1.13
[+] HTTP Status: 200
[+] Response JSON: {"model":"typesafe/jev-1.13","answers":{"is_safe":{"type":"noul","noul":0.89}}}
```

### Step 3: Install Globally Across All Workspaces
To protect every project on your machine without copying files:
```cmd
:: Create directory junctions (no admin privileges needed)
cmd /c mklink /J "%USERPROFILE%\.gemini\config\hooks" "%CD%\.agents\hooks"
cmd /c mklink /J "%USERPROFILE%\.gemini\config\skills" "%CD%\.agents\skills"
cmd /c mklink /J "%USERPROFILE%\.gemini\config\protocols" "%CD%\.agents\protocols"

:: Create configuration links
cmd /c mklink "%USERPROFILE%\.gemini\config\hooks.json" "%CD%\.agents\hooks.json"
cmd /c mklink "%USERPROFILE%\.gemini\config\.env" "%CD%\.agents\.env"
```
Reload Antigravity: Press <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>P</kbd> $\rightarrow$ **`Developer: Reload Window`**.

---

## 6. CLI Management & Rule Auditing

All safety decisions, user overrides, and active learning statistics are stored locally in SQLite (`~/.gemini/config/safety_decisions.db`).

### Inspect Security Audit & Stats
```cmd
cmd /c python %USERPROFILE%\.gemini\config\hooks\safety_db.py --review
```

### Inspect Speculative Prefetch & Ambiguity Feedback
```cmd
cmd /c python %USERPROFILE%\.gemini\config\hooks\safety_db.py --review-speculative
```

### List All Active Saved Rules
```cmd
cmd /c python %USERPROFILE%\.gemini\config\hooks\safety_db.py --list
```

### Add a Permanent Allow Rule
```cmd
cmd /c python %USERPROFILE%\.gemini\config\hooks\safety_db.py --allow "docker compose*" --tool run_command
```

### Test Command Resolution Against Shield & DB
```cmd
cmd /c python %USERPROFILE%\.gemini\config\hooks\safety_db.py --test-cmd "cmd /c git reset --hard"
```

### Prune Old Decision Logs & Expired Rules
```cmd
cmd /c python %USERPROFILE%\.gemini\config\hooks\safety_db.py --prune --days 30
```

---

## 7. Knowledge Items (KI) Workflows

The Knowledge Item Engine captures repository-local architectural precedents and automatically mounts them into Turn 1 when relevant.

### Capture an Invariant
```cmd
cmd /c python .agents/hooks/jev_ki_engine.py --learn --title "Speculative Fan-Out Protocol" --summary "Batches 4 questions in ~110ms to prefetch git diffs." --domain "tool_harness"
```

### Distill Knowledge From Git Commits
```cmd
cmd /c python .agents/hooks/jev_ki_engine.py --distill
```

### List Active Knowledge Precedents
```cmd
cmd /c python .agents/hooks/jev_ki_engine.py --list
```
