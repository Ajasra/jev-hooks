# `.agents/` — Machine-Native Agent Harness Architecture

This directory serves as the canonical configuration, lifecycle hook suite, protocol library, and skill repository for **TypeSafe AI Jev** within **Google Antigravity 2.0** and cross-compatible agent harnesses (OpenCode, Claude Desktop, Codex).

---

## 1. Directory Layout

```text
.agents/
├── AGENTS.md                  ← Multi-agent workspace persona & execution invariants
├── README.md                  ← This architecture document
├── hooks.json                 ← Lifecycle hook registration (PreInvocation, PreToolUse)
├── .env.example               ← Template for API keys (OpenRouter / TypeSafe AI)
├── knowledge/                 ← Project-scoped Knowledge Items (git-versioned, zero cross-repo leak)
│   └── ki_<id>/               ← Isolated pattern: metadata.json + artifacts/architectural_pattern.md
├── hooks/                     ← Machine-native System One hook implementations (0 external deps)
│   ├── env_loader.py          ← Dual-provider credentials, endpoint routing, debug logging
│   ├── jev_safety_gate.py     ← PreToolUse: Invariant Shield + SQLite memory + Jev blast radius
│   ├── jev_skill_router.py    ← PreInvocation: Two-tier dynamic skill disclosure (~90ms)
│   ├── jev_speculative_router.py ← PreInvocation: 4-question speculative batch & ambiguity arbiter (~220ms)
│   ├── jev_compactor.py       ← Session GC: Verbatim context compactor replacing tool dumps
│   ├── jev_ki_engine.py       ← PreInvocation: Fast KI triage & auto-mounting + closed-loop distillation (~70ms)
│   └── safety_db.py           ← SQLite storage for safety decisions, rule memory & speculative feedback
├── protocols/                 ← Canonical architectural protocols & invariant specifications
│   ├── system-one-balance-protocol.md ← "Augment, Don't Handcuff" anti-bureaucracy protocol
│   └── documentation-standard-protocol.md ← Narrative standards, audience segmentation & unified RFC taxonomy
└── skills/                    ← Modular skills discovered dynamically across workspace & globally
    ├── doc-architect/         ← Standards auditor & author for user/dev documentation & RFCs
    │   └── SKILL.md
    ├── skill-architect/       ← Interactive creator, refactorer, and auditor for agent skills
    │   ├── SKILL.md
    │   └── references/sample-skill.md
    ├── system-one-balance-protocol/ ← Actionable checklist referencing the canonical protocol
    │   └── SKILL.md
    └── typesafe-ai/           ← Official TypeSafe AI vendor skill & live documentation navigator
        └── SKILL.md
```

---

## 2. Machine-Native Lifecycle Hooks

| Hook File | Lifecycle Phase | Latency | Core Responsibility |
| :--- | :--- | :--- | :--- |
| **[`jev_safety_gate.py`](hooks/jev_safety_gate.py)** | `PreToolUse` | ~0ms–80ms | 3-stage defense: Deterministic Invariant Shield (`rmdir /s`, `git reset --hard`) $\rightarrow$ SQLite memory $\rightarrow$ Jev blast radius judgment. |
| **[`jev_skill_router.py`](hooks/jev_skill_router.py)** | `PreInvocation` | ~95ms | Two-tier progressive disclosure: injects full body ($\ge 0.80$) or lightweight soft hint ($0.50 \le P < 0.80$) to eliminate prompt bloat. |
| **[`jev_speculative_router.py`](hooks/jev_speculative_router.py)** | `PreInvocation` | ~220ms | Parallel 4-question batch: speculatively prefetches git diffs or test logs, handles bare URL triage, and provides recency-aware ambiguity scoring. |
| **[`jev_compactor.py`](hooks/jev_compactor.py)** | Session GC | ~270ms | Verbatim context compactor replacing repetitive tool dumps with 300-char receipts while keeping 100% of user discourse and code verbatim. |
| **[`jev_ki_engine.py`](hooks/jev_ki_engine.py)** | `PreInvocation` & Distillation | ~70ms | Dual-engine: sub-70ms pre-flight triage with Turn-1 auto-mounting ($\ge 0.70$) + closed-loop distillation and deduplication on commit/`/learn`. |

---

## 3. Global Antigravity Integration

All subdirectories in `.agents/` are linked globally into `%USERPROFILE%\.gemini\config` via directory junctions:

```cmd
:: 1. Link hooks, skills, and protocols
cmd /c mklink /J "%USERPROFILE%\.gemini\config\hooks" "d:\01_GIT\Jev\.agents\hooks"
cmd /c mklink /J "%USERPROFILE%\.gemini\config\skills" "d:\01_GIT\Jev\.agents\skills"
cmd /c mklink /J "%USERPROFILE%\.gemini\config\protocols" "d:\01_GIT\Jev\.agents\protocols"

:: 2. Link configuration and secrets
cmd /c mklink "%USERPROFILE%\.gemini\config\hooks.json" "d:\01_GIT\Jev\.agents\hooks.json"
cmd /c mklink "%USERPROFILE%\.gemini\config\.env" "d:\01_GIT\Jev\.agents\.env"
```

*Edits made anywhere in this directory immediately protect and enhance every workspace on the machine.*

---

## 4. Architectural Invariants

1. **Augment, Don't Handcuff**: Hooks must never paralyze foundation models with imperative tool lockouts (`DO NOT CALL TOOLS`) or amnesiac ambiguity halts on routine follow-up turns. Consult [`protocols/system-one-balance-protocol.md`](protocols/system-one-balance-protocol.md).
2. **Zero External Dependencies**: All hooks use standard library Python (`urllib`, `json`, `pathlib`, `sqlite3`, `re`).
3. **Windows Shell Invariant**: Shell commands executed via hooks or agent tools on Windows must always use `cmd /c` to ensure clean process termination and EOF signal delivery.

---

## 5. Knowledge Item Lifecycle Engine (`jev_ki_engine.py`)

The KI Engine enforces **strict project-level isolation by default**, versioning all architectural precedents directly in `.agents/knowledge/` with zero cross-repository contamination.

### CLI Examples & Usage

```cmd
:: 1. List all active project-scoped Knowledge Items
cmd /c python .agents/hooks/jev_ki_engine.py --list

:: 2. Explicitly capture an architectural invariant into workspace knowledge
cmd /c python .agents/hooks/jev_ki_engine.py --learn --title "Speculative Fan-Out Protocol" --summary "Batches 4 questions in ~110ms to prefetch git diffs." --domain "tool_harness"

:: 3. Distill knowledge automatically from the last git commit diff
cmd /c python .agents/hooks/jev_ki_engine.py --distill

:: 4. Pipe a diff directly for automated distillation
git diff HEAD~1..HEAD | python .agents/hooks/jev_ki_engine.py --distill
```

### PreInvocation Turn-1 Auto-Mounting Telemetry

When an incoming developer prompt matches an established project precedent with confidence $\ge 0.70$, the pattern is auto-mounted before Turn 1 starts, saving 5–10s of exploratory file reading:

```html
<system_preflight_hook name='jev_ki_engine'>
> **Jev KI Pre-Flight**: Auto-mounted relevant architectural precedent `ki_20260925_134914_tool_harness` (Conf: 0.94).

<ki_context id='ki_20260925_134914_tool_harness'>
# System One Speculative Fan-Out Protocol
...
</ki_context>
</system_preflight_hook>
```

When no KIs match ($P < 0.40$), the hook emits a deterministic Clean Assert to stop exploratory hesitation:

```html
<system_preflight_hook name='jev_ki_engine'>
> **Jev KI Pre-Flight**: Automated check confirmed no repository Knowledge Items apply. Proceed directly to fresh investigation without searching KIs.
</system_preflight_hook>
```

