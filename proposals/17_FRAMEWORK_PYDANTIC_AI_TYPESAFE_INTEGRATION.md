# Framework Reference: Pydantic AI's Native TypeSafe (Jev) Integration

## 1. Overview

[Pydantic AI](https://pydantic.dev/docs/ai/models/typesafe/) includes native, first-class support for TypeSafe's Jev model through [`TypeSafeModel`](https://pydantic.dev/docs/ai/api/models/typesafe/#pydantic_ai.models.typesafe.TypeSafeModel) (`pip install "pydantic-ai-slim[typesafe]"` or model string `'typesafe:jev-latest'`).

Pydantic AI demonstrates how an industry-standard Python agent framework structures the boundary between **System One decision models (Jev)** and **System 2 generative LLMs**.

---

## 2. Core Mechanism: Schema-as-Questions Mapping

In Pydantic AI, **each field of a Pydantic model automatically maps to an independent Jev question**:

```python
from typing import Literal
from enum import IntEnum
from pydantic import BaseModel, Field
from pydantic_ai import Agent, UseEnumMemberDocstrings

class Clarity(UseEnumMemberDocstrings, IntEnum):
    """Rubric for release note clarity."""
    opaque = 0     # Leaves reader none the wiser
    partial = 1    # Explains some, leaves obvious questions
    actionable = 2 # Reader could act on it

class PRTriage(BaseModel):
    """Structured decision output filled by Jev in one request."""
    urgent: bool = Field(description="Does this need attention within 1 hour?")
    category: Literal['bug', 'feature', 'refactor', 'security'] = Field(description="Primary category")
    clarity_score: Clarity = Field(description="Grade the quality of the PR description")

agent = Agent('typesafe:jev-latest', output_type=PRTriage)
result = agent.run_sync("URGENT: memory leak in auth middleware causing OOM crashes")
```

### Type Mapping Table in Pydantic AI

| Python Type | Jev Primitive | Question Behavior |
| :--- | :--- | :--- |
| `bool` | `Noul` | Calibrated yes/no probability ($0.0$ to $1.0$). Rounds against `typesafe_boolean_threshold` (default 0.5). |
| `Literal[...]` or `Enum` | `Choice` | Selects one option from candidate strings; returns probability distribution and confidence. |
| `IntEnum` with docstrings | `Score` | Evaluates against an ordered rubric scale ($0$ to $N$). |
| `float` with `ge=0, le=1` | `Noul` | Returns the raw, unrounded probability. |
| `list[Literal[...]]` | Parallel `Noul`s | Fans out to one yes/no question per option. |
| `dict[Literal, bool]` | Parallel `Noul`s | Maps each candidate option to its true/false probability. |
| `Union[ModelA, ModelB]` | Route `Choice` | Evaluates which model schema to fill in a second request. |

---

## 3. Four Key Architecture Patterns from Pydantic AI

### Pattern 1: Tool Execution Safety Gate (`before_tool_execute` Hook)
Pydantic AI intercepts tool calls before execution using in-process hooks:

```python
from pydantic_ai import Agent, RunContext, SkipToolExecution, ToolDefinition
from pydantic_ai.capabilities import Hooks
from pydantic_ai.messages import ToolCallPart

class Handling(BaseModel):
    irreversible: bool = Field(description="Would running this destroy data or leak secrets?")

judge = Agent('typesafe:jev-latest', output_type=Handling)

async def judge_tool_call(ctx: RunContext, *, call: ToolCallPart, tool_def: ToolDefinition, args: dict):
    verdict = await judge.run(f"{tool_def.name}: {args}")
    if verdict.output.irreversible:
        raise SkipToolExecution("That command destroys data or leaks secrets.")
    return args

agent = Agent('openai:gpt-5', capabilities=[Hooks(before_tool_execute=judge_tool_call)])
```

### Pattern 2: Per-Step Model Escalation (`SelectModel`)
Rather than choosing a model once at the beginning of a run, Pydantic AI allows the agent to evaluate conversation history **before each step**:

```python
from pydantic_ai.capabilities import SelectModel

async def select_model(ctx: ModelSelectionContext) -> Model:
    # Jev reads history and routes simple steps to fast model, hard steps to capable model
    picked = await router.run(message_history=ctx.messages)
    return capable_model if picked.output == 'capable' else fast_model

agent = Agent(capabilities=[SelectModel(select_model)])
```

### Pattern 3: Runtime Candidate Action Selection (`candidates(screen, targets)`)
When candidates are only known at runtime (e.g. interactive elements on a web page):
- Pydantic AI constructs callable output functions at runtime.
- Jev selects the function to call.
- **The candidate Jev picks *is* what runs**, eliminating the need for a separate dispatch table.

### Pattern 4: Confidence-Gated Fallback (`FallbackModel`)
```python
def unsure(response: ModelResponse) -> bool:
    confidence = (response.provider_details or {}).get('confidence', {})
    return any(value < 0.8 for value in confidence.values())

model = FallbackModel('typesafe:jev-latest', 'openai:gpt-5', fallback_on=[ModelAPIError, unsure])
```
If Jev is confident ($>0.8$), the decision costs ~100ms and pennies. If uncertain, it automatically falls back to an expensive frontier model.

---

## 4. Key Takeaways for Antigravity

1. **Adopt Pydantic AI's Rule**: *"The prompt is only what is being judged, and the question belongs on the output type."*
2. **First-Class In-Process Hooks**: Antigravity can replicate `before_tool_execute` using Jev to enforce platform constraints (such as Windows `cmd /c` compliance) and intercept destructive commands without custom model training.
3. **Pydantic Model Cleanliness**: Modeling tool schemas and routing criteria as Pydantic classes gives type safety, IDE autocompletion, and Jev execution all in one standard Python definition.
