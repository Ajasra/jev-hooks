# AI-Writing Tell Catalog & Patterns

Detection patterns and regex guidelines for the Anti-Slop Editor.

---

## 1. Negative Parallelism (The "Not X, but Y" Family)

```regex
not (just|only|merely|simply|solely) [^.;]{2,80}(but|it'?s| — )
isn'?t (just|only|merely|simply|about) 
it'?s not (a|an|the|that|about|just) [^.;]{2,80}(it'?s|but)
(is|was|are|were)n'?t about [^.;]{2,60}\. (it|this|that)'?s about
less about [^.;]{2,60}(than|and more about)
more than (just|a mere|simply) 
not because [^.;]{2,80}but because
the (question|point|issue|problem|goal|real [a-z]+) is(n'?t| not) (whether|about|just|if)
gone are the days
(here|this)'?s the (thing|kicker|catch|twist)
— not [^—.;]{2,60}, but 
```

**Triage**: Delete the negative half. State the active assertion directly.

---

## 2. Abstract Institutional Phrasing & Vaporware

```regex
\boperationaliz(e|es|ed|ing|ation)\b
\b(modular|scalable) adaptation\b
\b(multi-?stakeholder|socio-?technical) ecosystem(s)?\b
\b(multidimensional|conceptual|methodological) framework\b
\bsystemic integration\b
\b(synergistic|strategic) alignment\b
\bactionable insights\b
\bserves? to (bridge|elucidate|illuminate|dismantle)\b
\bholistic approach to\b
\bstrategic imperative\b
\bseamless integration across\b
```

**Triage**: Replace with the literal mechanism, tools, code execution, or physical constraints.

---

## 3. Plausible Completeness & Balanced Triads

```regex
\bacross (urban, suburban, and rural|technical, ethical, and|social, cultural, and|local, regional, and)\b
\bacross (diverse|varied|multiple) (contexts|domains|settings|geographies|landscapes|sectors)\b
\bfrom [^.;]{3,40}, to [^.;]{3,40}, and [^.;]{3,40}\b
\baddressing (technical, social, and economic|cultural, political, and institutional)\b
```

**Triage**: Cut decorative balance. Name the exact primary focus and its friction.

---

## 4. Broad Omnibus Claims & Puffed Significance

```regex
\b(profound|far-reaching|crucial) implications for (the future of|our understanding)\b
\bspeaks? to broader questions (surrounding|regarding|of)\b
\bsheds? light on the (complex|intricate|multifaceted)\b
\bunderscores? the (enduring|critical) importance of\b
\bplays? a (pivotal|vital|central) role in (shaping|transforming|navigating)\b
\bserves? as a (vital|crucial|critical) bridge between\b
\ba testament to the (power|enduring|complex)\b
\bpoised to (transform|reshape|revolutionize)\b
```

**Triage**: Replace with concrete findings, numbers, latencies, or error boundaries.

---

## 5. Unhuman Vocabulary & Marketing Buzzwords

```regex
\b(grounded|firmly grounded) in\b
\b(delve|delves|delving)\b
\btapestry\b
\b(testament|stands as a testament)\b
\b(multifaceted|multifacetedness)\b
\b(interplay|interplays)\b
\b(nexus|nexuses)\b
\b(elucidate|elucidates|elucidating)\b
\b(beacon|beacons)\b
\b(catalyst|catalysts)\b
\b(linchpin|linchpins)\b
\b(nuanced|nuance)\b
\b(holistic|holistically)\b
\b(robust|robustness)\b
\b(seamless|seamlessly)\b
\b(intricate|intricacies)\b
\b(pivotal|paramount)\b
\b(underscore|underscores|underscoring)\b
\b(resonate|resonates)\b
\b(foster|fosters|fostering)\b
\b(harness|harnesses|harnessing)\b
\b(spearhead|spearheads)\b
\b(bespoke)\b
\b(plethora|myriad)\b
\b(conduit|conduits)\b
\b(panacea)\b
\b(transformative)\b
\bever.?(evolving|changing)\b
\bfast.?paced (world|environment)\b
\bcutting.?edge\b
\bgame.?chang(er|ing)\b
\belevate(s|d)? (the|your)\b
\bshowcas(e|es|ing)\b
```

---

## 6. Hedging & Throat-Clearing

```regex
it'?s (worth|important) (to note|noting|to remember|to consider)
(that|it) (being )?said,
while (it'?s|this is) (true|important)
arguably
in many ways
at its core
in essence
essentially,
ultimately,
in conclusion
in summary
to sum(marize| up)
needless to say
let'?s (dive|unpack|explore|take a look)
whether you('re| are) [^.;]{2,60} or 
```
