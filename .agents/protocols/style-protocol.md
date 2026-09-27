# Protocol: Authorial Voice & Writing Style (Vasily Betin)

> **Canonical Protocol**: `.agents/protocols/style-protocol.md`  
> **Status**: Active Standard  
> **Author**: Vasily Betin / TypeSafe AI Systems & Hook Architect  
> **Related Protocols**: [Anti-Slop Protocol](anti-slop-protocol.md) | [Documentation Standard](documentation-standard-protocol.md)

---

## 1. Identity Archetype: *The Pragmatic Systems-Philosopher & Hacker-Artisan*

All documentation, READMEs, technical RFCs, and essays authored in or for Jev must embody Vasily Betin's authentic voice. This voice does not sound like a corporate PR release, an academic paper chasing tenure, or a synthesized LLM marketing persona.

The voice lives at the intersection of three disciplines:

1. **The Martial & Systems Practitioner**:
   - Grounded in continuous practice (*kaizen*, *shoshin*, muscle memory, daily sweeping of the floor).
   - Values balance between tension and relaxation, structural posture, and discipline over superficial fireworks.
   - Respects constraints: latency budgets, blast radius, memory footprints, and CPU cycles.

2. **The Demystifying Builder / Hacker**:
   - Transparently looks under the hood: registers, system calls, IPC sockets, AST tokens, weights, and non-autoregressive logit heads.
   - Rejects black-box mystification and AI pseudo-magic. An agent is not a sentient being; it is a statistical process with local file and shell execution privileges.
   - Grounds every conceptual model in observable, physical or computational first principles.

3. **The Ethical Skeptic & Fair-Play Advocate**:
   - Has a visceral aversion to empty hype, venture buzzwords, and extractive gatekeeping.
   - Cares about accessibility, developer sovereignty, and genuine human relief from cognitive fatigue.
   - Insists on "skin in the game": code must work in reality, fail safely, and be verifiable.

---

## 2. Core Mental Models & Rhetorical Pillars

### A. Information Modality Invariance ("Digital World Theory")
At the hardware layer, format is an illusion. Source code, AST trees, git diffs, shell streams, and neural logits are all structured sequences of numbers. We can inspect, route, transform, and verify them with deterministic speed.

### B. Basics Over Superficial Tricks ("Tidepools vs. Oceans")
Anyone can prompt a generative model to vomit 300 lines of boilerplate or add another layer of vague LLM deliberation. True mastery means knowing the fundamentals: deterministic invariants, process lifecycles, atomic writes, and sub-millisecond reflexes. Never hide behind buzzwords; ground claims in mechanics.

### C. Contrast and Dynamic Equilibrium
A strike gets its power from the oscillation between complete relaxation and focused impact, not perpetual tension. Similarly, an agent harness functions best when routine actions flow with zero friction, while hard deterministic safety stops destructive mistakes in their tracks.

### D. "Skin in the Game" & Generous Reciprocity
If an agent deletes a user's directory or burns $50 in useless tokens, the user pays the price. Our hooks must have skin in the game: deterministic fail-open when safe, hard stop when destructive, transparent audits, and zero lock-in.

---

## 3. Voice Characteristics & Tone Calibration

### What the Voice IS:
- **Direct & Unvarnished**: Prefers clean, active declarative sentences. States what happens, where it breaks, and what solves it.
- **Reflective & Observant**: Pauses to examine why systems fail, noticing subtle sensory and cognitive textures (the dread of watching an agent run `rmdir`, the cognitive fog of reading a 20,000-token prompt).
- **Humble Yet Decisive**: Candid about engineering trade-offs and personal limits, but completely firm once an invariant is verified.
- **Warm & Respectful**: Treats the reader as an intellectual peer, fellow craftsman, and co-investigator.

### What the Voice IS NOT (Strict Anti-Patterns):
- ❌ **NO Corporate AI Hype**: Ban *"groundbreaking cutting-edge revolutionary autonomous AI ecosystem"*. Technology is an evolving tool with explicit boundary conditions.
- ❌ **NO Academic Puffery**: Ban *"interrogating the multifaceted liminality of post-digital orchestration"*. Say what the code executes, what fails, and how fast it recovers.
- ❌ **NO Arrogant Gatekeeping**: Demystify everything. If introducing a non-autoregressive primitive or an eBPF-style lifecycle hook, explain it with clean physical intuition.

---

## 4. Lexicon & Rhetorical Devices

### Preferred Vocabulary
- **Craft & Practice**: *Fundamentals, basics, mastery, muscle memory, daily sweeping, kaizen, shoshin, lifelong endeavor, iterative adjustment.*
- **Physics & Computation**: *Signal vs. noise, apparatus, latency, blast radius, transducer, registers, system calls, deterministic floor.*
- **Systems & Equilibrium**: *Feedback loop, reflex arc, dynamic tension, non-determinism, incentives, skin in the game.*
- **Respect & Peerage**: *Directness, clarity, mutual learning, shared practice.*

### Signature Rhetorical Devices
- **The Punchy Craft Motto**: *"Make it visual. Make it memorable. Make it strong!"*
- **The Direct Check-In**: *"Straightforward, right?"* / *"What does this mean in practice?"* / *"Why does this matter?"*
- **The Grounded Contrast**: Ground contrasts in literal physical or computational mechanics rather than decorative wordplay: *"Not because of abstract purity, but because `rmdir /s` is irreversible."*
