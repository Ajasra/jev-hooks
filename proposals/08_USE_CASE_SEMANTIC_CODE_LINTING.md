# Use Case: Semantic Code Linting in CI/CD & Pre-Commit

## 1. Problem Statement

Modern software projects rely on static linters (ESLint, Prettier, Ruff, Clippy) to enforce syntax, formatting, and type correctness. However, static linters cannot evaluate **semantic and architectural rules**:
- *"All database queries in this service must pass through the repository pattern, never direct ORM calls."*
- *"API response DTOs must never expose raw database entity instances."*
- *"Custom hooks in this React codebase must wrap state transitions with error boundaries."*

Teams currently enforce these through manual human PR reviews, which:
- Slow down release cycles (PR review queues).
- Are error-prone and inconsistent across reviewers.
- Cannot be automated with traditional regex or AST linters without writing brittle, high-maintenance custom plugins.

---

## 2. Core Idea: Jev Semantic PR Diff Scorer

Jev evaluates git diffs and modified files against natural language policy rules in CI/CD pipelines (e.g. GitHub Actions, GitLab CI):
- **Fast Execution**: Evaluates 10–20 architectural rules across PR diffs in ~150–250ms.
- **Calibrated Scores**: Returns a `PASS`, `WARN`, or `FAIL` decision with exact confidence scores.
- **Zero Hallucinated Comments**: Your CI script maps Jev's structured decisions directly to PR review status and inline comments.

```mermaid
flowchart TD
    GitDiff["PR Git Diff + Changed Files"] --> JevLinter["Jev Semantic CI Linter (~150ms)"]
    TeamGuidelines["Repo Architectural Rules & Coding Standards"] --> JevLinter
    
    subgraph ParallelChecks ["Concurrent Rule Evaluation"]
        R1["Noul: Violates Repository Pattern?"]
        R2["Noul: Exposes Raw DB Entities in API DTO?"]
        R3["Noul: Omits Error Handling on External API Call?"]
        Severity["Score: 1-5 Architectural Impact"]
    end
    JevLinter --> ParallelChecks
    
    ParallelChecks --> CIAction{"Rule Violation Detected?"}
    
    CIAction -->|Violations Found (Severity ≥ 3)| BlockPR["Block CI / Request Changes:<br/>Add automated inline PR comment citing team guideline"]
    CIAction -->|Minor Warning (Severity = 2)| PostNotice["Post Informational PR Comment"]
    CIAction -->|All Pass| GreenCI["Pass CI Check Immediately"]
```

---

## 3. Specification & Rules Definition

```typescript
const architecturalLintRules = {
  repository_pattern_violation: {
    type: "noul",
    instructions: "Does this code diff introduce direct database access or queries in controller/service layers, bypassing the established repository pattern?"
  },
  leaks_internal_entities: {
    type: "noul",
    instructions: "Does any public API endpoint or controller method return raw internal database entities instead of dedicated response DTOs?"
  },
  unhandled_external_failures: {
    type: "noul",
    instructions: "Does this diff make outbound HTTP/RPC calls without proper try/catch handling, timeout configurations, or fallback logic?"
  },
  architectural_risk: {
    type: "score",
    instructions: "Score the severity of architectural guideline violations introduced by this change.",
    levels: {
      "1": "Clean diff; adheres fully to team conventions and patterns.",
      "2": "Minor stylistic or naming inconsistency; non-blocking.",
      "3": "Moderate convention drift (e.g. redundant logic, missing type guards).",
      "4": "Serious architectural violation (e.g. layer bypass, missing error boundary).",
      "5": "Critical design regression (e.g. exposed credentials, severe anti-pattern)."
    }
  }
};
```

---

## 4. Architectural Value

1. **Automated Architectural Enforcement**: Frees human senior engineers from checking boilerplate conventions during PR reviews.
2. **Instant Developer Feedback**: Developers get semantic feedback in CI in seconds rather than waiting hours for human peer review.
3. **No Brittle Custom AST Rules**: Define complex architectural policies in plain English rather than writing thousands of lines of custom Babel or ESLint AST parser plugins.
