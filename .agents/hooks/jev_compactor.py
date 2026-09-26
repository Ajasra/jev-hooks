#!/usr/bin/env python3
"""Compatibility API backed by the shared trajectory compactor."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from jev.core.compaction import checkpoint

PRESERVE_RECENT_MESSAGES = 4


def compact_trajectory(messages: list[dict]) -> list[dict]:
    return checkpoint(messages, preserve_recent=PRESERVE_RECENT_MESSAGES)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python jev_compactor.py <trajectory_json_file>")
    source = Path(sys.argv[1])
    print(json.dumps(compact_trajectory(json.loads(source.read_text(encoding="utf-8")))))
