"""
Zero-dependency environment variable loader for Antigravity Jev hooks.
Automatically checks:
1. .agents/.env
2. .env (project root)
3. Direct environment variables
"""

import os
from pathlib import Path

def load_env():
    candidates = [
        Path(".agents/.env"),
        Path(".env"),
        Path(__file__).resolve().parent.parent / ".env",
        Path(__file__).resolve().parent / ".env",
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            try:
                for line in p.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
                break
            except Exception:
                pass

# Run on import
load_env()
