---
name: anti-slop-editor
description: Aggressively edits drafts to eliminate AI slop, robotic parallelisms, corporate filler, and uniform sentence cadence.
concerns: [prose, documentation]
---
# Anti-Slop Editor (`anti-slop-editor`)

> **Governing Protocols**: [`.agents/protocols/anti-slop-protocol.md`](../../protocols/anti-slop-protocol.md) | [`.agents/protocols/style-protocol.md`](../../protocols/style-protocol.md)

This skill mechanically scans, diagnoses, and rewrites text to purge statistical AI fingerprints and align prose with Vasily Betin's authorial voice (*Pragmatic Systems-Philosopher & Hacker-Artisan*).

---

## Phase 0: Setup & Reference Loading

1. Load [`.agents/protocols/style-protocol.md`](../../protocols/style-protocol.md) for voice calibration and vocabulary preferences.
2. Load [`.agents/protocols/anti-slop-protocol.md`](../../protocols/anti-slop-protocol.md) for core rules.
3. Load [`references/tells.md`](references/tells.md) for detection patterns.

---

## Phase 1: Ingest & Diagnostics

1. Read the target document or text block.
2. Run mechanical pattern scans across the 6 primary diagnostic categories:
   - **Negative parallelism** ("not X, but Y")
   - **Abstract institutional phrasing** ("operationalize", "socio-technical ecosystem")
   - **Plausible completeness** (symmetrical triad checklists)
   - **Broad omnibus claims** ("profound implications for the future of")
   - **Unhuman academic/marketing puffery** (`delve`, `tapestry`, `multifaceted`, `seamless`, `pivotal`, etc.)
   - **Hedging & throat-clearing** ("it is worth noting", "at its core", "in essence")
3. Inspect structural rhythm:
   - **Cadence**: flag runs of 3+ consecutive sentences within $\pm 4$ words of the same length.
   - **Formatting**: flag bold text scatter, emoji header spam, and "Term: definition" bullet clusters.

---

## Phase 2: Meaning-First Rewrite Loop

Rule: Never fix an AI pattern by paraphrasing the pattern. Fix by asking: *What physical or computational event is happening here?*, then stating that event plainly.

### Triage Rules:
1. **Strip negative parallelisms**: Assert the positive claim directly. Name names and numbers if comparing against a specific alternative.
2. **Expose the mechanism**: Replace vague abstractions with specific tools, file paths, IPC contracts, or measurements.
3. **Break symmetrical lists**: Keep the strongest, most relevant item. Discard filler items added just to make a list have three parts.
4. **Vary sentence cadence**: Deliberately inject short 3–6 word punchy sentences between longer analytical paragraphs.
5. **Calibrate tone**: Ensure the text speaks as a craftsman explaining an apparatus to a peer—no condescension, no breathless hype.

---

## Phase 3: Verification & Output

1. Re-scan the rewritten text against `references/tells.md`.
2. Confirm zero high-frequency puffery tokens.
3. Confirm cadence variance passes (no uniform sentence blocks).
4. Save the file or output the clean, de-slopped prose.
