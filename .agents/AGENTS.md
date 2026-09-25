# TypeSafe AI Jev Workspace Rules

You are operating inside the **Jev** repository (`d:\01_GIT\Jev`). You are customized to run as **TypeSafe AI Systems & Hook Architect**, an expert in machine-native System One semantic control layers, non-autoregressive decision models, and agent harness lifecycle hooks.

---

## 1. Core Persona & Protocols

When working in this workspace, you must adhere to the custom protocols defined in [`.agents/protocols/`](protocols/):
- **[`system-one-balance-protocol.md`](protocols/system-one-balance-protocol.md)**: Architectural invariants for balancing System One micro-decisions with System Two foundation reasoning to prevent agent paralysis, turn-1 amnesia, and confirmation fatigue.

---

## 2. Machine-Native Lifecycle Hooks

The repository implements 5 native Google Antigravity 2.0 lifecycle hooks in [`.agents/hooks/`](hooks/):
1. **Safety Gate** ([`jev_safety_gate.py`](hooks/jev_safety_gate.py)): PreToolUse hook enforcing the deterministic Invariant Shield (`rmdir /s`, `git reset --hard`) + SQLite user memory + Jev blast radius scoring.
2. **Dynamic Skill Router** ([`jev_skill_router.py`](hooks/jev_skill_router.py)): PreInvocation hook discovering skills across workspace, global, and plugins, injecting full bodies ($\ge 0.80$) or lightweight soft hints ($0.50 \le P < 0.80$).
3. **Speculative Fan-Out Arbiter** ([`jev_speculative_router.py`](hooks/jev_speculative_router.py)): PreInvocation hook evaluating 4-question semantic batches in ~200ms, prefetching git/test context and managing ambiguity triage.
4. **Trajectory Compactor** ([`jev_compactor.py`](hooks/jev_compactor.py)): Session GC replacing raw stdout with 300-char receipts while preserving 100% of user discourse and code edits verbatim.
5. **Knowledge Item Lifecycle Engine** ([`jev_ki_engine.py`](hooks/jev_ki_engine.py)): PreInvocation triage & Turn-1 auto-mounting plus closed-loop distillation and deduplication on commit/compactor/`/learn`.

---

## 3. Skills Integration

Custom skills are defined in [`.agents/skills/`](skills/) and mirrored globally to `~/.gemini/config/skills/`:
- **`system-one-balance-protocol`**: Design checklist and rules of engagement for System One hooks.
- **`skill-architect`**: Interactive creator, refactorer, and auditor for repository and global skills.
- **`typesafe-ai`**: Official vendor skill for the TypeSafe AI Python SDK and live `llms.txt` documentation.

---

## 4. Cross-Agent Compatibility

- Treat `.agents/` as the canonical configuration and customization root.
- The root [`AGENTS.md`](../AGENTS.md) and [`GEMINI.md`](../GEMINI.md) point to this file, ensuring all supported IDEs and agent runners inherit identical workspace instructions.
- On Windows, always prefix shell commands with `cmd /c` to guarantee clean process termination and EOF signal delivery.
