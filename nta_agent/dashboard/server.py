"""Thin stdlib HTTP layer serving the dashboard page + read-only JSON APIs."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from nta_agent.dashboard.data import read_json_array, read_state, tail_events
from nta_agent.dashboard.names import build_label, load_build_names
from nta_agent.dashboard.page import INDEX_HTML
from nta_agent.runtime.commands import append_command
from nta_agent.runtime.config import RuntimeConfig

_VALID_TRACK = {"pawn", "policy", "equip"}


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
        elif parsed.path == "/api/decisions":
            self._json(200, read_json_array(cfg.decisions_path))
        elif parsed.path == "/api/equipment":
            self._json(200, read_json_array(cfg.equipment_path))
        elif parsed.path == "/api/armies":
            self._json(200, read_json_array(cfg.armies_path))
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        cfg = self.server.cfg
        if parsed.path != "/api/command":
            self._json(404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, TypeError):
            self._json(400, {"ok": False, "error": "bad json"})
            return
        action = body.get("action")
        if action == "equip":
            if (not body.get("pawn_id") and body.get("pawn_id") != 0) or not body.get("equip_uid"):
                self._json(400, {"ok": False, "error": "equip needs pawn_id + equip_uid"})
                return
            cmd = {"action": "equip", "pawn_id": int(body["pawn_id"]),
                   "equip_uid": str(body["equip_uid"]),
                   "skin_id": int(body.get("skin_id", 0) or 0),
                   "attack_speed": int(body.get("attack_speed", 0) or 0)}
            cid = append_command(cfg.commands_path, cmd)
            self._json(200, {"ok": True, "id": cid})
            return
        track = body.get("track")
        if action not in ("select", "reroll") or track not in _VALID_TRACK:
            self._json(400, {"ok": False, "error": "bad action/track"})
            return
        if action == "select" and "ceri_id" not in body:
            self._json(400, {"ok": False, "error": "select needs ceri_id"})
            return
        cmd = {"action": action, "track": track, "lv": int(body.get("lv", 0) or 0)}
        if action == "select":
            cmd["ceri_id"] = int(body["ceri_id"])
        cid = append_command(cfg.commands_path, cmd)
        self._json(200, {"ok": True, "id": cid})


def serve(cfg: RuntimeConfig, port: int, *, host: str = "127.0.0.1") -> DashboardServer:
    return DashboardServer((host, port), Handler, cfg)
