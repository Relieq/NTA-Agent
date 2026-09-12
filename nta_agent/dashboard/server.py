"""Thin stdlib HTTP layer serving the dashboard page + read-only JSON APIs."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from nta_agent.dashboard.data import read_state, tail_events
from nta_agent.dashboard.names import build_label, load_build_names
from nta_agent.dashboard.page import INDEX_HTML
from nta_agent.runtime.config import RuntimeConfig


class DashboardServer(ThreadingHTTPServer):
    def __init__(self, addr, handler, cfg: RuntimeConfig):
        super().__init__(addr, handler)
        self.cfg = cfg
        self.build_names = load_build_names()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence stderr access logs
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self):
        parsed = urlparse(self.path)
        cfg = self.server.cfg
        if parsed.path == "/":
            self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
        elif parsed.path == "/api/state":
            state = read_state(cfg.snapshot_path)
            if state.get("ok"):
                for b in state.get("builds", []):
                    b["name"] = build_label(self.server.build_names, b.get("id", 0))
            self._json(200, state)
        elif parsed.path == "/api/events":
            q = parse_qs(parsed.query)
            try:
                n = int(q.get("n", ["50"])[0])
            except ValueError:
                n = 50
            n = max(1, min(n, 500))
            self._json(200, tail_events(cfg.event_log_path, n))
        else:
            self._json(404, {"error": "not found"})


def serve(cfg: RuntimeConfig, port: int, *, host: str = "127.0.0.1") -> DashboardServer:
    return DashboardServer((host, port), Handler, cfg)
