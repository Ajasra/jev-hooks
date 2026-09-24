"""
Zero-dependency environment variable loader for Antigravity Jev hooks.
Automatically checks:
1. .agents/.env
2. .env (project root)
3. Direct environment variables (supports both TYPESAFE_API_KEY and OPENROUTER_API_KEY)
"""

import os
import sys
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

def get_client_config():
    """
    Returns (api_key, endpoint, model, headers) with automated detection for:
    - Direct TypeSafe AI API (https://api.typesafe.ai/v1/systemone)
    - OpenRouter API (https://openrouter.ai/api/v1/systemone with typesafe/jev-latest)
    """
    typesafe_key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "").strip()

    # Detect OpenRouter key prefix (sk-or-v1-) even if set as TYPESAFE_API_KEY
    is_openrouter = False
    if openrouter_key:
        is_openrouter = True
        api_key = openrouter_key
    elif typesafe_key.startswith("sk-or-v1-"):
        is_openrouter = True
        api_key = typesafe_key
    else:
        api_key = typesafe_key

    # Determine default endpoint and model
    if is_openrouter:
        default_endpoint = "https://openrouter.ai/api/v1/systemone"
        default_model = "typesafe/jev-1.13"
    else:
        default_endpoint = "https://api.typesafe.ai/v1/systemone"
        default_model = "jev-latest"

    endpoint = os.environ.get("TYPESAFE_ENDPOINT", "").strip()
    if not endpoint or (is_openrouter and "api.typesafe.ai" in endpoint):
        endpoint = default_endpoint

    model = os.environ.get("JEV_MODEL", "").strip()
    if not model or (is_openrouter and model in ("jev-latest", "typesafe/jev-latest")):
        model = default_model


    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    if is_openrouter or "openrouter.ai" in endpoint:
        headers["HTTP-Referer"] = "https://github.com/google/antigravity"
        headers["X-Title"] = "Antigravity Jev Integration"

    return api_key, endpoint, model, headers

