# Jev: System One Semantic Control for AI Coding Harnesses

[![System One](https://img.shields.io/badge/Architecture-System%20One%20Semantic%20Control-blue.svg)](https://docs.typesafe.ai)
[![Harnesses](https://img.shields.io/badge/Harnesses-Google%20Antigravity%20%7C%20OpenAI%20Codex-orange.svg)](./proposals/RFC-24_CORE_shared_harness_runtime.md)
[![OpenRouter](https://img.shields.io/badge/Provider-OpenRouter%20%7C%20TypeSafe-purple.svg)](https://openrouter.ai/~typesafe/jev-latest)
[![P95 Latency](https://img.shields.io/badge/P95%20Latency-%3C120ms-brightgreen.svg)](https://docs.typesafe.ai)
[![Zero Pip Dependencies](https://img.shields.io/badge/Dependencies-Zero%20Pip%20Core-success.svg)](https://python.org)

**Machine-native System One semantic control layer for Google Antigravity and OpenAI Codex.** Provides sub-120ms dynamic skill dispatch, autonomous execution safety guardrails, speculative diff prefetching, universal output verification, and verbatim context compaction powered by **TypeSafe AI's Jev model**.

---

## 1. Problem: The System Two Cognitive Bottleneck

Autonomous coding agents grant generative models (Gemini, Claude, GPT) direct local execution privileges. However, delegating routine micro-decisions exclusively to heavy, autoregressive **System Two** models causes severe friction:
1. **Prompt Bloat & Token Waste**: Advertising 50+ domain skills in prompts burns 5,000–25,000 tokens on *every single turn*.
2. **Accidental Destruction**: Models occasionally emit dangerous commands (`rmdir /s`, `git reset --hard`) without an authoritative deterministic barrier.
3. **Turn-1 Latency & Amnesia**: Exploratory file grep and status discovery waste 3–5 turns before real coding begins.
4. **Hallucinated Interfaces**: Models invent plausible but nonexistent API signatures and parameters, triggering costly debugging loops.

---

## 2. Inspiration: Biological Reflex Arcs & Microkernel Probes

In human biology and modern operating systems, high-frequency survival checks do not consult conscious deliberation. Sub-conscious **reflex arcs** and **eBPF probes** execute at hardware speeds in milliseconds.

Translating this division of labor to AI harnesses: **Deterministic code enforces safety, Jev handles fast semantic micro-decisions, and primary foundation models focus purely on deep reasoning and code synthesis.**

> **Grounding Axiom**: *Meaning is in the context, not in the message.* Decisions require a situated 4-layer **Context Envelope** (intent, environment, history, precedents) rather than bare prompt strings. See **[docs/PHILOSOPHY.md](docs/PHILOSOPHY.md)**.

---

## 3. Solution: TypeSafe Jev System One Primitives

**Jev** is TypeSafe AI's non-autoregressive decision model:
* **Sub-120ms P95 Latency**: Evaluates parallel questions against application state in **70ms–120ms** (190x faster than LLMs).
* **Extreme Efficiency**: **$0.042 / 1M input tokens** with **free unmetered outputs** (440x cheaper than LLMs).
* **Guaranteed Typing**: Zero schema validation failures across native `Choice`, `Score`, and `Noul` primitives.
* **Unified Dual-Harness Runtime**: One shared Python implementation ([`src/jev/`](src/jev/)) powers **both Google Antigravity and OpenAI Codex** ([RFC-24](proposals/RFC-24_CORE_shared_harness_runtime.md)) with zero policy drift.

---

## 4. Visual Production Proof

### PreToolUse Safety Gate (Intercepting Destructive Actions)
When an agent attempts `cmd /c rmdir /s /q benchmarks\tests`, Jev evaluates blast radius in ~80ms, halting execution and rendering an interactive confirmation modal:

![Jev Safety Gate Intercept Modal](./proposals/assets/jev_safety_gate_intercept_modal.png)

### PreInvocation Speculative Pre-Flight (Eliminating Turn-1 Roundtrips)
Before primary reasoning starts, Jev speculatively evaluates context and auto-prefetches git diffs or pytest diagnostics into Turn 1:

![Jev Speculative Pre-Flight Badge](./proposals/assets/jev_speculative_preflight_badge.png)

```text
> **Jev Speculative Pre-Flight**: Attached speculative evidence (git_prefetch (P=0.77) in 266ms).
```

### PreInvocation Dynamic Skill Routing (Zero Prompt Bloat)
Jev evaluates user requests in ~95ms, selectively mounting matching canonical skills from [`.agents/skills/`](.agents/skills/) without advertising unused skills:

```text
> **Activated Skill**: `app-security`
```

---

## 5. Quick Start (60 Seconds)

### Step 1: Install Package & Configure API Key
```cmd
cmd /c python -m pip install --user -e ".[mcp]"
cmd /c setx OPENROUTER_API_KEY "sk-or-v1-your_openrouter_api_key_here"
```

### Step 2: Verify Diagnostics & Offline Tests
```cmd
cmd /c python -m jev doctor --cwd .
cmd /c python -m pytest -q
```

### Step 3: Connect to Your Agent Harness
* **Google Antigravity**: Link canonical hooks and skills into global user configuration:
  ```cmd
  cmd /c mklink /J "%USERPROFILE%\.gemini\config\hooks" "%CD%\.agents\hooks"
  cmd /c mklink /J "%USERPROFILE%\.gemini\config\skills" "%CD%\.agents\skills"
  cmd /c mklink "%USERPROFILE%\.gemini\config\hooks.json" "%CD%\.agents\hooks.json"
  ```
  Reload window (<kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>P</kbd> $\rightarrow$ **`Developer: Reload Window`**).
* **OpenAI Codex**: Configured via repository [`.codex/hooks.json`](.codex/hooks.json) and [`.codex/config.toml`](.codex/config.toml).

---

## 6. Machine-Native Lifecycle Capabilities

| Capability | Lifecycle Phase | Latency | Core Responsibility | Deep Spec |
| :--- | :---: | :---: | :--- | :---: |
| **Safety Gate** | `PreToolUse` | ~0–80ms | Invariant Shield + Jev blast radius; renders IDE modal or Codex deny. | [RFC-04](proposals/RFC-04_CORE_safety_and_tool_guardrail.md) |
| **Speculative Arbiter** | `PreInvocation` | ~220ms | Parallel batch: prefetches git diffs / test logs; recency ambiguity triage. | [RFC-21](proposals/RFC-21_EXT_speculative_fan_out.md) |
| **Dynamic Skill Router** | `PreInvocation` | ~95ms | Progressive disclosure: injects full body ($\ge 0.80$) or lightweight hint. | [RFC-02](proposals/RFC-02_CORE_dynamic_skill_dispatcher.md) |
| **Knowledge Engine** | `PreInvocation` | ~70ms | Sub-70ms relevance scoring with Turn-1 auto-mounting of repository KIs. | [RFC-03](proposals/RFC-03_CORE_knowledge_item_matcher.md) |
| **Output Verifier** | `PreToolUse` / Tool | ~90ms | Sub-100ms API symbol & citation verification; catches hallucinated methods. | [RFC-07](proposals/RFC-07_USE_CASE_output_citation_verification.md) |
| **Semantic Code Lint** | Tool / CLI | ~120ms | KI-style architectural rule evaluation over bounded git diffs. | [RFC-08](proposals/RFC-08_USE_CASE_semantic_code_linting.md) |
| **Context Compactor** | Session GC | ~270ms | Verbatim GC: prunes stale logs to 300ch receipts; preserves 100% of code. | [RFC-01](proposals/RFC-01_CORE_verbatim_context_compactor.md) |

---

## 7. Documentation Hub

* 📖 **[User Guide & Operational Manual](docs/USER_GUIDE.md)**: Onboarding, interactive modals, CLI auditing, and dual-harness setup.
* 🧠 **[Philosophy & Grounding Axioms](docs/PHILOSOPHY.md)**: Meaning in context, System One division of labor, and the Context Envelope.
* 🛠️ **[Architecture & Technical Specification](docs/ARCHITECTURE.md)**: Ports-and-adapters design, IPC schemas, SQLite database structures, and latency budgets.
* 📋 **[Master Proposals & RFC Index (25 Specs)](proposals/README.md)**: Unified technical specifications and blueprints (`RFC-01` to `RFC-25`).
* 📜 **[System One Balance Protocol](.agents/protocols/system-one-balance-protocol.md)**: Anti-bureaucracy guidelines keeping semantic micro-decisions fast and non-blocking.

---

## License & Attribution

* Released under the [MIT License](LICENSE).
* **Jev** is a proprietary System One foundation model developed by **TypeSafe AI** ([docs.typesafe.ai](https://docs.typesafe.ai)).
* **Google Antigravity** & **OpenAI Codex** are supported agentic coding harnesses.
