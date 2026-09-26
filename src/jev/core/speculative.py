"""Turn preflight that gathers bounded, read-only repository evidence."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from jev.contracts import ContextItem, Outcome, Result
from jev.services.client import DecisionClient


def _git_context(cwd: Path) -> str:
    try:
        process = subprocess.run(
            ["git", "-c", f"safe.directory={cwd.as_posix()}", "status", "--short"],
            cwd=str(cwd), capture_output=True, text=True, timeout=0.15,
            encoding="utf-8", errors="replace",
        )
        return (process.stdout or process.stderr).strip()[:3000]
    except (OSError, subprocess.SubprocessError):
        return ""


def evaluate(
    prompt: str,
    cwd: Path,
    prior_context: str,
    client: DecisionClient | None,
    timeout: float,
) -> Result:
    started = time.monotonic()
    if not prompt:
        return Result(feature="speculative", feature_version="1")
    needs_git = any(term in prompt.lower() for term in ("diff", "change", "commit", "review", "status"))
    ambiguity = 0.0
    continuation = bool(prior_context)
    if client is not None:
        try:
            questions = {
                "needs_git": {
                    "type": "noul",
                    "instructions": "Would current git status materially help answer this request?",
                }
            }
            if prior_context:
                questions.update({
                    "ambiguous": {
                        "type": "noul",
                        "instructions": "Considering prior_turn_context, is the requested target still unclear?",
                    },
                    "continuation": {
                        "type": "noul",
                        "instructions": "Is this request a clear continuation of prior_turn_context?",
                    },
                })
            answers = client.evaluate(
                {"request": prompt, "prior_turn_context": prior_context[-3000:]},
                questions,
                timeout,
            )
            needs_git = float(answers.get("needs_git", {}).get("noul", 0.0)) >= 0.65
            ambiguity = float(answers.get("ambiguous", {}).get("noul", 0.0))
            continuation = float(answers.get("continuation", {}).get("noul", 0.0)) >= 0.65
        except Exception:
            pass
    result = Result(
        outcome=Outcome.ABSTAIN,
        feature="speculative",
        feature_version="1",
        data={"needs_git": needs_git, "ambiguity": ambiguity, "continuation": continuation},
        duration_ms=(time.monotonic() - started) * 1000,
    )
    if needs_git:
        git = _git_context(cwd)
        if git:
            result.context.append(ContextItem("speculative", f"Current git status:\n{git}", 60))
    if ambiguity >= 0.70 and not continuation and not prior_context:
        result.context.append(ContextItem(
            "speculative",
            "The request may be underspecified. Ask one focused question only if repository inspection cannot identify the target.",
            30,
        ))
    result.duration_ms = (time.monotonic() - started) * 1000
    return result
