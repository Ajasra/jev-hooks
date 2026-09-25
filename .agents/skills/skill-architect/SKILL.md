---
name: skill-architect
description: >
  Inventories, creates, refactors, and audits Antigravity and Jev skills using structured blueprints and the System One balance protocol.
  Use when asked to create, edit, audit, or reorganize agent skills.
concerns: [system-one-balance]
---

# Skill Architect Protocol

The Skill Architect manages the lifecycle of agent skills across workspace ([`.agents/skills/`](../)) and global (`~/.gemini/config/skills/`) repositories.

---

## Phase 0: Setup and Protocols
1. Read referenced protocols matching the `concerns` field in YAML frontmatter.
2. For `system-one-balance`, consult [`.agents/protocols/system-one-balance-protocol.md`](../../protocols/system-one-balance-protocol.md).
3. Review the canonical template in [`.agents/skills/skill-architect/references/sample-skill.md`](references/sample-skill.md).

---

## Phase 1: Ingest and Check
1. Determine the task mode:
   - **Create**: New skill name specified, target directory does not yet exist.
   - **Update / Refactor**: Existing skill directory found, modifications requested.
   - **Audit**: Review existing skill catalog for compliance with the balance protocol.
2. Validate skill naming:
   - Must be `kebab-case` (e.g. `skill-architect`, `system-one-balance-protocol`).
   - Lowercase alphanumeric characters and hyphens only.
3. Validate prompt trigger:
   - Ensure `description` in YAML frontmatter is a crisp, 1-2 sentence specification of what the skill does and the exact scenarios when Jev should activate it.

---

## Phase 2: Processing

### Case A: Create New Skill
1. Create directory: `.agents/skills/[skill-name]/`.
2. Author `SKILL.md` following the [sample-skill blueprint](references/sample-skill.md):
   - Valid YAML frontmatter (`name`, `description`, `concerns`).
   - **Phase 0**: Setup and Protocols.
   - **Phase 1**: Ingest and Check (pre-flight checks, input validation).
   - **Phase 2**: Processing (numbered active imperative steps).
   - **Phase 3**: The System One Balance Pass.
   - **Phase 4**: Output Execution & Verification.
3. Create auxiliary directories if required:
   - `references/` for blueprints, schema specs, or reference catalogs.
   - `examples/` for input/output demonstrations.

### Case B: Update Existing Skill
1. Read `.agents/skills/[skill-name]/SKILL.md`.
2. Apply requested functional changes while preserving the 5-phase structure.
3. Verify that YAML frontmatter retains valid `name` and `description` fields.

### Case C: Audit Skill Catalog
1. Scan all directories under `.agents/skills/`.
2. Check for:
   - Valid YAML frontmatter.
   - Absence of imperative tool bans (`DO NOT CALL TOOLS`).
   - Clean mechanical instructions without fluff.

---

## Phase 3: The System One Balance Pass
Before writing or committing any `SKILL.md`:
1. Check against [`.agents/protocols/system-one-balance-protocol.md`](../../protocols/system-one-balance-protocol.md).
2. **Eliminate Bureaucracy**:
   - Ensure the skill does not command the agent to lock down read tools.
   - Ensure the skill does not force confirmation modals for routine tasks.
   - Ensure instructions are actionable, sequential, and concise.

---

## Phase 4: Output Execution & Verification
1. Save `SKILL.md` to `.agents/skills/[skill-name]/SKILL.md`.
2. Confirm the skill is instantly accessible globally via the `~/.gemini/config/skills/` junction.
3. Test dynamic discovery against Jev:
   ```cmd
   cmd /c python -c "import subprocess, json; p = subprocess.Popen(['python', '.agents/hooks/jev_skill_router.py'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True); out, _ = p.communicate(json.dumps({'prompt': 'I need to design a new agent skill'})); print(out[:300])"
   ```
