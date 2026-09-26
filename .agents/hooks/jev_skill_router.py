#!/usr/bin/env python3
"""Deprecated Antigravity entry point; routing lives in jev.core.skills."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from jev.cli import main


if __name__ == "__main__":
    raise SystemExit(main(["hook", "--harness", "antigravity"]))
