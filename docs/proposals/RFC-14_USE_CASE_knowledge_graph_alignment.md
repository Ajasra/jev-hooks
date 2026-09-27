# Use Case: Knowledge Graph Entity Alignment & Deduplication

## 1. Problem Statement

Organizations unifying multiple internal databases, customer catalogs, or codebase dependencies frequently encounter entity fragmentation:
- Same person or company across two systems: *"Google LLC, Mountain View"* vs *"Alphabet Inc. - Google Div"*.
- Same package or library: `"@anthropic-ai/sdk"` vs `"anthropic"` in differing package manifests.
- Inconsistent names, typos, legacy ID formats, and missing metadata.

Traditional resolution methods struggle:
- **String Distance (Levenshtein / Jaccard)**: Fails on semantic aliases (e.g. "Big Blue" vs "IBM").
- **Vector Embedding Similarity**: Fails on subtle contradictions (e.g. two companies with identical names located in different countries).
- **Generative LLMs**: Far too expensive and slow to run over millions of candidate pairs.

---

## 2. Core Idea: High-Throughput Semantic Alignment with Jev

Jev combines a holistic `Score` question with specific companion `Noul` questions across candidate pairs in high-throughput batches:
- **`Score`**: Measures overall semantic equivalence (1–5).
- **Companion `Noul`s**: Probe individual attributes for contradictions (e.g. country mismatch, version conflict, category mismatch).

```mermaid
flowchart LR
    Pair["Candidate Pair:<br/>Entity A + Entity B"] --> JevMatcher["Jev Alignment Engine (~70ms)"]
    
    subgraph AlignmentEval ["Simultaneous Evaluations"]
        EquivScore["Score: 1-5 Identity Match"]
        NameMatch["Noul: Do names refer to the same entity?"]
        FieldConflict["Noul: Do attributes contain hard factual contradictions?"]
    end
    JevMatcher --> AlignmentEval
    
    AlignmentEval --> ResolutionLogic{"Evaluate Match vs. Conflict"}
    
    ResolutionLogic -->|Score ≥ 4 and Conflict < 0.2| AutoMerge["Auto-Merge / Link Entities in Graph"]
    ResolutionLogic -->|Conflict ≥ 0.6| FlagDistinct["Declare Distinct Entities"]
    ResolutionLogic -->|Ambiguous (Confidence < 0.7)| HumanQueue["Route to Human Data Steward Queue"]
```

---

## 3. Specification & Questions

```typescript
function buildEntityAlignmentQuestions(entityA: any, entityB: any) {
  return {
    identity_score: {
      type: "score",
      instructions: "Rate how likely it is that Entity A and Entity B refer to the exact same real-world entity, company, or software artifact.",
      levels: {
        "1": "Definitely distinct, unrelated entities.",
        "2": "Superficially similar or same industry, but clearly different entities.",
        "3": "Ambiguous evidence or insufficient metadata to determine.",
        "4": "Strongly likely to be the same entity despite naming variations.",
        "5": "Definitive, exact match for the same entity."
      }
    },
    has_hard_attribute_contradiction: {
      type: "noul",
      instructions: "Do Entity A and Entity B have conflicting attributes (such as incompatible founding dates, opposing physical locations, or conflicting parent organizations) that make identity impossible?"
    },
    name_variation_explained: {
      type: "noul",
      instructions: "Can the difference between the names be explained by standard abbreviation, legal suffix, translation, or acquisition branding?"
    }
  };
}
```

---

## 4. Architectural Value

1. **High-Throughput Batch Processing**: At ~$0.042 per million input tokens, millions of candidate pairs can be resolved for tens of dollars.
2. **Explainable Contradiction Detection**: Companion Nouls surface *why* two items disagree rather than just returning an opaque cosine distance number.
3. **Calibrated Confidence**: Low-confidence pairs are routed to human review queues with clear probabilities attached.
