"""Private stdio worker for native adapters; policy remains in run_hook."""

from __future__ import annotations

import json
import sys
from collections import OrderedDict

from jev.services.paths import Settings
from jev.services.storage import Storage

MAX_REQUEST_CHARS = 4 * 1024 * 1024


def serve(harness: str) -> int:
    from jev.cli import run_hook

    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({"ready": True}), flush=True)
    stores: OrderedDict[str, Storage] = OrderedDict()
    while True:
        line = sys.stdin.readline(MAX_REQUEST_CHARS + 1)
        if not line:
            return 0
        if len(line) > MAX_REQUEST_CHARS:
            print("Jev worker request exceeded framing limit", file=sys.stderr)
            return 1
        request_id = None
        try:
            request = json.loads(line)
            request_id = request["request_id"]
            payload = request["payload"]
            if not isinstance(payload, dict):
                raise ValueError("worker payload must be an object")
            settings = Settings.load(payload.get("cwd") or None)
            key = str(settings.db_path)
            storage = stores.pop(key, None) or Storage(settings.db_path)
            stores[key] = storage
            while len(stores) > 8:
                stores.popitem(last=False)
            response = {"request_id": request_id, "result": run_hook(harness, payload, settings, storage)}
        except Exception as exc:
            response = {"request_id": request_id, "error": type(exc).__name__}
        print(json.dumps(response, separators=(",", ":")), flush=True)
