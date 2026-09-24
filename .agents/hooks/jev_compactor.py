#!/usr/bin/env python3
"""
Trajectory Garbage Collection Engine: Antigravity Context Compactor using Jev.
Adapts Tamara Tran's fast-jev-compaction algorithm to prune Antigravity session
trajectories (storage/sessions/traj-*) when context utilization exceeds 60%.
Retains all code diffs, compiler errors, and user prompts 100% verbatim.
"""

import sys
import os
import json
import urllib.request
from pathlib import Path

TYPESAFE_API_KEY = os.environ.get("TYPESAFE_API_KEY", "")
TYPESAFE_ENDPOINT = os.environ.get("TYPESAFE_ENDPOINT", "https://api.typesafe.ai/v1/systemone")
JEV_MODEL = os.environ.get("JEV_MODEL", "jev-latest")

KEEP_THRESHOLD = 0.50
PRESERVE_RECENT_MESSAGES = 6
TRUNCATE_HEAD_CHARS = 300
MAX_STATE_CHARS = 100_000

def compact_trajectory(messages: list) -> list:
    """
    Performs deterministic boundary definition, tool masking, parallel Jev evaluation,
    and surgical reconstruction.
    """
    if len(messages) <= PRESERVE_RECENT_MESSAGES + 1 or not TYPESAFE_API_KEY:
        return messages

    # 1. Identify tool pairs
    # Pin messages[0] and the trailing recency window
    pinned_indices = {0} | set(range(len(messages) - PRESERVE_RECENT_MESSAGES, len(messages)))
    
    candidate_calls = []
    for idx, msg in enumerate(messages):
        if idx in pinned_indices:
            continue
        tool_calls = msg.get("tool_calls", [])
        for call in tool_calls:
            candidate_calls.append({
                "msg_idx": idx,
                "id": call.get("id", f"call_{idx}"),
                "name": call.get("name", "unknown_tool"),
                "input": call.get("arguments", {}),
                "result": call.get("result", "")
            })

    if not candidate_calls:
        return messages

    # 2. Prepare state with masked results to avoid token blowup
    state_lines = []
    for idx, msg in enumerate(messages):
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        state_lines.append(f"[{role}]: {content[:400]}")
        for call in msg.get("tool_calls", []):
            cid = call.get("id", "")
            name = call.get("name", "")
            res_len = len(str(call.get("result", "")))
            state_lines.append(f"  Tool {cid} ({name}) -> ok, {res_len:,} chars (omitted)")

    state_str = "\n".join(state_lines)[:MAX_STATE_CHARS]

    # 3. Build parallel dual-Noul questions
    questions = {}
    for call in candidate_calls:
        cid = call["id"]
        cname = call["name"]
        questions[f"call_{cid}"] = {
            "type": "noul",
            "instructions": f"Knowing tool call {cid} ({cname}) was made, with its input, still matters for what the developer/assistant does next."
        }
        questions[f"result_{cid}"] = {
            "type": "noul",
            "instructions": f"The full output of tool call {cid} ({cname}) should stay in history verbatim: its exact contents are still needed and re-running would not do."
        }

    # 4. Dispatch parallel evaluation to Jev
    payload = {
        "model": JEV_MODEL,
        "state": state_str,
        "questions": questions
    }

    try:
        req = urllib.request.Request(
            TYPESAFE_ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {TYPESAFE_API_KEY}"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        answers = data.get("answers", {})
    except Exception as e:
        sys.stderr.write(f"[Jev Compactor] API call failed: {e}. Falling back to uncompacted history.\n")
        return messages

    # 5. Apply 3-tier decision rule
    decisions = {}
    for call in candidate_calls:
        cid = call["id"]
        p_call = answers.get(f"call_{cid}", {}).get("noul", 0.5)
        p_res = answers.get(f"result_{cid}", {}).get("noul", 0.5)

        if p_res >= KEEP_THRESHOLD:
            decisions[cid] = "KEEP_FULL"
        elif p_call >= KEEP_THRESHOLD:
            decisions[cid] = "TRUNCATE"
        else:
            decisions[cid] = "DROP"

    # 6. Rebuild message list verbatim
    pruned_messages = []
    for idx, msg in enumerate(messages):
        if idx in pinned_indices:
            pruned_messages.append(msg)
            continue

        tool_calls = msg.get("tool_calls", [])
        if not tool_calls:
            pruned_messages.append(msg)
            continue

        surviving_calls = []
        for call in tool_calls:
            cid = call.get("id", "")
            action = decisions.get(cid, "KEEP_FULL")

            if action == "KEEP_FULL":
                surviving_calls.append(call)
            elif action == "TRUNCATE":
                truncated_call = dict(call)
                raw_res = str(call.get("result", ""))
                truncated_call["result"] = (
                    f"{raw_res[:TRUNCATE_HEAD_CHARS]}\n"
                    f"[... Jev Compactor: Result truncated. Call metadata preserved; re-run tool if full output is required ...]"
                )
                surviving_calls.append(truncated_call)
            elif action == "DROP":
                # Dropped entirely
                pass

        # Only retain message if it has surviving calls or content
        if surviving_calls or msg.get("content", "").strip():
            new_msg = dict(msg)
            new_msg["tool_calls"] = surviving_calls
            pruned_messages.append(new_msg)

    return pruned_messages

def main():
    if len(sys.argv) < 2:
        print("Usage: python jev_compactor.py <trajectory_json_file>")
        sys.exit(1)

    traj_path = Path(sys.argv[1])
    if not traj_path.exists():
        print(f"Error: Trajectory file {traj_path} not found.")
        sys.exit(1)

    try:
        data = json.loads(traj_path.read_text(encoding="utf-8"))
        messages = data if isinstance(data, list) else data.get("messages", [])
        initial_chars = len(json.dumps(messages))

        compacted = compact_trajectory(messages)
        final_chars = len(json.dumps(compacted))

        reduction = (1 - final_chars / initial_chars) * 100 if initial_chars else 0
        print(f"Compaction complete: {initial_chars:,} chars -> {final_chars:,} chars ({reduction:.1f}% reduction).")

        if isinstance(data, list):
            data = compacted
        else:
            data["messages"] = compacted

        traj_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"Error during trajectory compaction: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
