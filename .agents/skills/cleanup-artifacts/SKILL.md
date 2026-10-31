---
name: cleanup-artifacts
description: >
  Clean up temporary session files, tool caches, browser recordings, and conversation bloat across agent harnesses after user confirmation.
scope: global
---

# Cleanup Artifacts & Session Hygiene

Use this skill after task implementation and verification are complete, when the user requests or confirms cleaning up session bloat across agent harnesses (Antigravity, Claude Code, Codex, OpenCode/Aider).

## Principles

1. **User Confirmation Required**: Never purge conversation histories, scratch files, or caches without explicit user intent.
2. **Preserve Rules, Agents, MCPs & Projects**: Never remove configuration files, rules, custom agents, MCP tool schemas, database migrations, or project repositories.
3. **Preserve Active Session**: If operating inside an active agent conversation, preserve the active session ID's brain and transcript.

## Targets by Harness

### 1. Antigravity
- **Past Conversations**: Purge inactive conversation databases in `%USERPROFILE%\.gemini\antigravity\conversations\`.
- **Inactive Brains**: Purge non-active UUID folders in `%USERPROFILE%\.gemini\antigravity\brain\`.
- **Temporary Tool & Browser Traces**: Purge `%USERPROFILE%\.gemini\antigravity\browser_recordings\*`, `cache\*`, `artifacts\*`, `implicit\*`, and `sidecar_data\*`.
- **Installers & Staged Updates**: Purge `%LOCALAPPDATA%\Temp\antigravity-stable-user-x64` and `%LOCALAPPDATA%\antigravity-updater\*`.
- **Web & GPU Caches (Deep Clean)**: Optionally flush `Cache`, `Code Cache`, `GPUCache`, and `CachedData` inside `%APPDATA%\Antigravity` and `%APPDATA%\Antigravity IDE`.

### 2. Claude Code
- **Caches & Transcripts**: Clear inactive sessions in `~/.claude/artifacts/`, ephemeral scratchpads, and debug log files.
- **Preserve**: Keep `~/.claude/settings.json`, configured skills, and authenticated profiles.

### 3. Codex & OpenCode / Aider
- **Scratch & Diffs**: Purge stale patch chunks (`.patch`, `.diff.tmp`), transient tool logs, and cached completions in `.codex/cache/` or `.opencode/`.

### 4. Workspace Level
- Purge intermediate scratch test scripts (`scratch/*.ps1`, `scratch/*.py`) created solely for one-off debugging.
- Purge standard build/test cache directories generated during task verification (e.g., `.pytest_cache`, `.coverage`, `__pycache__`, `node_modules/.cache`) when confirmed.

## Workflow

1. **Assess & Report**: Check current file counts and sizes in the relevant harness locations. Present the summary to the user.
2. **Confirm Scope**: Clarify whether to run standard cleanup (session data, past artifacts, temp files) or deep cleanup (including IDE/browser GPU caches).
3. **Execute**: Remove the target paths cleanly using non-interactive commands.
4. **Report Outcome**: Output a before-and-after reclaimed disk space summary.
