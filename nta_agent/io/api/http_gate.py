"""HTTP gate client for NTA bootstrap endpoints (server info, notices, hot-update).

The game reaches these at ``https://<domain>:8080<path>`` via POST with a JSON body
(see docs/PROTOCOL.md). Read-only; no session required.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Any


class HttpGate:
    def __init__(self, domain: str, port: int = 8080, use_ssl: bool = True):
        scheme = "https" if use_ssl else "http"
        self.base = f"{scheme}://{domain}:{port}"

    def post(self, path: str, data: dict[str, Any] | None = None, timeout: float = 12) -> Any:
        if not path.startswith("/"):
            path = "/" + path
        body = json.dumps(data or {}).encode("utf-8")
        req = urllib.request.Request(
            self.base + path, data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
