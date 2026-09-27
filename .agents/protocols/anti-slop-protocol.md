# Protocol: Anti-Slop Directive & Prose Calibration

> **Canonical Protocol**: `.agents/protocols/anti-slop-protocol.md`  
> **Status**: Active Standard  
> **Related Protocols**: [Authorial Voice & Style](style-protocol.md) | [Documentation Standard](documentation-standard-protocol.md)  
> **Executable Skill**: [`.agents/skills/anti-slop-editor/`](../skills/anti-slop-editor/SKILL.md)

---

## 1. Core Purpose

Autonomous coding models default to a bland, synthetic statistical register characterized by empty contrastive parallelisms, corporate/academic puffery, symmetrical checklists, and uniform sentence rhythm. 

Every piece of documentation, README, proposal, and agent output in Jev must be strictly de-slopped prior to commit or user presentation.

---

## 2. The Six Tell Categories

### 1. Negative Parallelism (The "Not X, but Y" Reflex)
LLMs reach for negation-then-assertion once per paragraph to simulate depth. 
- *Banned variants*: *"not just X, but Y"*, *"it's not about X, it's about Y"*, *"less about X and more about Y"*, *"not only X but also Y"*, *"gone are the days"*, *"here's the kicker"*.
- **Triage**:
  - If the negation is a strawman: delete X, assert Y directly with evidence.
  - If the contrast is real: name specifically who claims X and why Y replaces it with concrete facts.
  - If the sentence asserts nothing substantive: delete the sentence entirely.

### 2. Abstract Institutional Phrasing & Bureaucratic Vaporware
Jargon that sounds authoritative while obscuring missing code, data, or physical mechanisms.
- *Banned tokens*: `operationalize`, `modular adaptation across varied contexts`, `socio-technical ecosystem`, `multidimensional framework`, `strategic alignment`, `actionable insights`, `holistic approach`, `value-driven paradigm`, `seamless integration`.
- **Triage**: Replace with the literal mechanism, tools, code, file paths, or data used. If no concrete reality exists, delete the sentence.

### 3. Plausible Completeness & Balanced Triad Checklists
Models generate symmetrical triplets across geographies, disciplines, or categories to appear exhaustive.
- *Examples*: *"in technical, ethical, and organizational dimensions"*; *"tested across urban, suburban, and rural settings"*.
- **Triage**: Force situated human commitment. Cut to the actual dimensions analyzed with distinct code and data. Remove decorative balance.

### 4. Broad Omnibus Claims & Puffed Significance
Expansive claims that sound momentous but make zero falsifiable assertions.
- *Banned tokens*: `profound implications for the future of`, `speaks to broader questions`, `sheds light on the intricate interplay`, `underscores the critical importance`, `plays a pivotal role in`, `serves as a vital bridge`, `a testament to the power of`, `poised to transform`.
- **Triage**: Replace with the concrete delta, exact latency reduction, or error boundary. State *what breaks* if this is ignored.

### 5. Unhuman Academic / Marketing Vocabulary
High-frequency statistical fingerprints of LLM generation:
- *Banned list*: `delve`, `tapestry`, `multifaceted`, `interplay`, `nexus`, `elucidate`, `beacon`, `catalyst`, `linchpin`, `nuanced`, `holistic`, `robust`, `seamless`, `meticulous`, `intricate`, `pivotal`, `underscore`, `resonate`, `foster`, `harness`, `spearhead`, `bespoke`, `plethora`, `conduit`, `panacea`, `transformative`, `fast-paced world`, `game-changer`, `elevate`.
- **Triage**: Replace with plain language, exact technical nouns/verbs, or delete.

### 6. Hedging & Throat-Clearing
Reflexive softeners added to avoid committing to a stance.
- *Banned openers*: *"It is worth noting that"*, *"That being said"*, *"At its core"*, *"In essence"*, *"Essentially"*, *"Ultimately"*, *"Needless to say"*, *"Let's dive in"*, *"Whether you are an X or a Y"*.
- **Triage**: State the claim directly or cut it.

---

## 3. Structural & Rhythm Invariants

1. **Cadence Variance**:
   - Uniform sentence length is a dead giveaway of synthetic text. 
   - **Hard Rule**: No run of 3+ consecutive sentences within $\pm 4$ words of each other.
   - Mix short 3–5 word assertions with detailed technical descriptions. Fragments are legal when used with precision.

2. **Formatting Restraint**:
   - **No bold scattered like glitter**: Do not bold every third word in body prose.
   - **No "Term: definition" bullet spam**: Use normal descriptive paragraphs unless presenting an actual reference dictionary.
   - **No emoji bullet salad** (🚀, ✅, 💡, ⚡) on technical specifications.
   - **Em-Dash Density**: Max 1 em-dash per 150 words. Never two in a single sentence.

3. **Information Integrity**:
   - De-slopping must never dilute precision, delete valid constraints, or drop code examples.
   - Ground assertions in concrete measurements (e.g. *"70ms–120ms P95 latency"*, *"< 150 lines"*, *"zero pip dependencies"*).
