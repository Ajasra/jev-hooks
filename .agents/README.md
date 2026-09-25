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
├── hooks/                     ← Machine-native System One hook implementations (0 external deps)
│   ├── env_loader.py          ← Dual-provider credentials, endpoint routing, debug logging
│   ├── jev_safety_gate.py     ← PreToolUse: Invariant Shield + SQLite memory + Jev blast radius
│   ├── jev_skill_router.py    ← PreInvocation: Two-tier dynamic skill disclosure (~90ms)
│   ├── jev_speculative_router.py ← PreInvocation: 4-question speculative batch & ambiguity arbiter (~220ms)
│   ├── jev_compactor.py       ← Session GC: Verbatim context compactor replacing tool dumps
│   └── safety_db.py           ← SQLite storage for safety decisions, rule memory & speculative feedback
├── protocols/                 ← Canonical architectural protocols & invariant specifications
│   └── system-one-balance-protocol.md ← "Augment, Don't Handcuff" anti-bureaucracy protocol
└── skills/                    ← Modular skills discovered dynamically across workspace & globally
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
