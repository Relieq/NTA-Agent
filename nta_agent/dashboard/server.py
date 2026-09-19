"""Thin stdlib HTTP layer serving the dashboard page + read-only JSON APIs."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from nta_agent.dashboard.data import read_json_array, read_state, tail_events
from nta_agent.dashboard.names import build_label, load_build_names
from nta_agent.dashboard.page import INDEX_HTML
from nta_agent.runtime.commands import append_command
from nta_agent.runtime.config import RuntimeConfig

_VALID_TRACK = {"pawn", "policy", "equip"}
_RES_KEYS = ("cereal", "timber", "stone", "iron", "gold", "stamina",
             "exp_book", "up_scroll", "fixator")

_STATIC_DIR = (Path(__file__).parent / "static").resolve()
_STATIC_TYPES = {".js": "text/javascript", ".mjs": "text/javascript",
                 ".css": "text/css", ".map": "application/json"}


def serve_static(relpath: str):
    """Return (status, content_type, body_bytes) for a file under the static dir.

    Guards against path traversal and non-whitelisted extensions. 404 on any miss.
    """
    ext = ("." + relpath.rsplit(".", 1)[-1]).lower() if "." in relpath else ""
    ctype = _STATIC_TYPES.get(ext)
    if not ctype:
        return 404, "text/plain", b"not found"
    try:
        target = (_STATIC_DIR / relpath).resolve()
        target.relative_to(_STATIC_DIR)  # raises if traversal escaped the dir
        body = target.read_bytes()
    except (ValueError, OSError):
        return 404, "text/plain", b"not found"
    return 200, ctype + "; charset=utf-8", body


def _chat_state():
    """Minimal state object the digest can read (chat needs no live resources)."""
    return SimpleNamespace(main_city_index=0,
                           resources=SimpleNamespace(**{k: 0 for k in _RES_KEYS}), raw={})


def handle_chat(cfg, message, *, history=None, propose=None):
    """Turn a chat instruction into a guarded profile edit: LLM -> sanitize ->
    apply -> persist profile.json -> queue a profile_edit command. Pure of HTTP."""
    from nta_agent.brain import llm as _llm
    from nta_agent.brain.digest import digest
    from nta_agent.brain.guard import sanitize_edits
    from nta_agent.brain.llm import BrainUnavailable
    from nta_agent.execution.profile import apply_edits, load_profile, save_profile
    propose = propose or _llm.propose
    profile = load_profile(cfg.profile_path)
    try:
        armies = json.loads(Path(cfg.armies_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        armies = []
    valid = {str(a.get("uid")) for a in armies}
    try:
        from nta_agent.data.config import GameConfig
        valid_build = set(GameConfig.load().in_city_build_ids())
    except Exception:
        valid_build = None
    dg = digest(_chat_state(), profile, armies)
    try:
        edits = propose(dg, profile, instruction=message, history=history or [])
    except BrainUnavailable as e:
        return {"ok": False, "error": "brain unavailable: %s" % e}
    except Exception as e:  # network/parse — surface, change nothing
        return {"ok": False, "error": str(e)}
    clean = sanitize_edits(edits, profile, valid, valid_build_ids=valid_build)
    apply_edits(profile, clean)
    save_profile(profile, cfg.profile_path)
    append_command(cfg.commands_path, {"action": "profile_edit", "edits": clean})
    return {"ok": True, "applied": clean, "rationale": (edits or {}).get("rationale", ""),
            "active": profile.army.get("active", ""),
            "presets": list(profile.army.get("presets") or {}),
            "notes": profile.notes}


def _valid_build_ids():
    try:
        from nta_agent.data.config import GameConfig
        return set(GameConfig.load().in_city_build_ids())
    except Exception:
        return None


def read_profile_view(cfg) -> dict:
    """Current profile plus building-name map + in-city catalogue (for the editor),
    filtered to the current game mode (room_type from the snapshot)."""
    from nta_agent.dashboard.names import load_build_names
    from nta_agent.execution.profile import load_profile
    profile = load_profile(cfg.profile_path)
    names = load_build_names()
    room_type = read_state(cfg.snapshot_path).get("room_type")
    try:
        from nta_agent.data.config import GameConfig
        ids = GameConfig.load().in_city_build_ids(room_type)
    except Exception:
        ids = sorted(_valid_build_ids() or set())
    catalogue = [{"id": bid, "name": names.get(bid, f"#{bid}")} for bid in ids]
    return {"active": profile.army.get("active", ""),
            "presets": list(profile.army.get("presets") or {}),
            "notes": profile.notes,
            "build": profile.build,
            "leveling": getattr(profile, "leveling", {}),
            "names": {str(k): v for k, v in names.items()},
            "catalogue": catalogue}


def read_territory_view(cfg) -> dict:
    """Own territory (main city, forts with pos + auto-support, garrisons) from the snapshot."""
    st = read_state(cfg.snapshot_path)
    mw = int(st.get("map_width") or 600)
    forts = [{"index": f["index"], "auto_support": f.get("auto_support", False),
              "x": f["index"] % mw, "y": f["index"] // mw}
             for f in (st.get("forts") or [])]
    return {"main_city": st.get("main_city_index", 0), "forts": forts,
            "garrisons": st.get("garrisons") or [], "map_width": mw}


def read_forts_view(cfg) -> dict:
    """Fort recommendations (owned count + recs) from forts.json, if present."""
    try:
        data = json.loads(Path(cfg.forts_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"owned_count": 0, "owned_cells": [], "accepted": [], "rejected": [],
                "enemy_cells": [], "enemy_cities": [], "frontier": [], "recommendations": [],
                "threats": [], "threat_summary": {"count": 0}}
    return {"owned_count": data.get("owned_count", 0),
            "owned_cells": data.get("owned_cells") or [],
            "accepted": data.get("accepted") or [],
            "rejected": data.get("rejected") or [],
            "enemy_cells": data.get("enemy_cells") or [],
            "enemy_cities": data.get("enemy_cities") or [],
            "frontier": data.get("frontier") or [],
            "recommendations": data.get("recommendations") or [],
            "threats": data.get("threats") or [],
            "threat_summary": data.get("threat_summary") or {"count": 0}}


def read_errors(cfg) -> dict:
    """Structured error summary (errors.jsonl) for a post-run review."""
    from nta_agent.runtime.errorlog import ErrorLog
    try:
        from nta_agent.data.config import GameConfig
        config = GameConfig.load()
    except Exception:
        config = None
    return ErrorLog(cfg.errors_path, config).summary()


def read_intel(cfg) -> dict:
    """Assemble the intel & advisory report (Phase I) from snapshot + forts.json,
    plus the brain's human-facing advice (Phase B)."""
    from nta_agent.execution.intel import build_report
    try:
        advice = json.loads(Path(cfg.brain_advice_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        advice = []
    return build_report(read_state(cfg.snapshot_path), read_forts_view(cfg),
                        brain_advice=advice)


def recompute_forts(cfg) -> dict:
    """Rewrite forts.json from its owned_cells + snapshot + decisions. No game I/O."""
    from nta_agent.data.config import GameConfig
    from nta_agent.execution.fort_advisor import plan_forts
    from nta_agent.runtime import fort_decisions
    try:
        fdj = json.loads(Path(cfg.forts_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        fdj = {}
    cells = fdj.get("owned_cells") or []
    terr = read_territory_view(cfg)
    mw = int(terr.get("map_width") or 600)
    owned = [int(y) * mw + int(x) for x, y in cells]
    main = int(terr.get("main_city") or 0)
    existing = [int(f["index"]) for f in terr.get("forts", [])]
    decisions = fort_decisions.load(cfg.fort_decisions_path)
    try:
        cap = GameConfig.load().max_count(2102)
    except Exception:
        cap = 1
    recs, accepted = plan_forts(main, owned, existing, decisions, cap, map_width=mw)
    payload = {"owned_count": len(owned), "owned_cells": cells,
               "accepted": sorted([i % mw, i // mw] for i in accepted),
               "rejected": sorted([i % mw, i // mw] for i, d in decisions.items()
                                  if d == "rejected"),
               # map layers are re-scanned by FortService, not here — carry them over
               "enemy_cells": fdj.get("enemy_cells") or [],
               "enemy_cities": fdj.get("enemy_cities") or [],
               "frontier": fdj.get("frontier") or [],
               "threats": fdj.get("threats") or [],
               "threat_summary": fdj.get("threat_summary") or {"count": 0},
               "recommendations": recs}
    Path(cfg.forts_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.forts_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
    return payload


def handle_profile_edit(cfg, edits: dict) -> dict:
    """Apply a structured (non-LLM) profile edit: sanitize -> persist -> queue command."""
    from nta_agent.brain.guard import sanitize_edits
    from nta_agent.execution.profile import apply_edits, load_profile, save_profile
    profile = load_profile(cfg.profile_path)
    # army.group is validated against real army uids; without them a group edit
    # (farm-group picker) would be filtered to empty. Read them from armies.json.
    try:
        armies = json.loads(Path(cfg.armies_path).read_text(encoding="utf-8"))
        valid_uids = {str(a.get("uid")) for a in armies if isinstance(a, dict)}
    except (OSError, ValueError):
        valid_uids = set()
    clean = sanitize_edits(edits, profile, valid_uids, valid_build_ids=_valid_build_ids())
    apply_edits(profile, clean)
    save_profile(profile, cfg.profile_path)
    append_command(cfg.commands_path, {"action": "profile_edit", "edits": clean})
    return {"ok": True, "applied": clean, "build": profile.build}


class DashboardServer(ThreadingHTTPServer):
    def __init__(self, addr, handler, cfg: RuntimeConfig):
        super().__init__(addr, handler)
        self.cfg = cfg
        self.build_names = load_build_names()
        self.chat_history = []
        from nta_agent.dashboard.supervisor import AgentSupervisor
        self.supervisor = AgentSupervisor(cfg)


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
        elif parsed.path == "/api/profile":
            self._json(200, read_profile_view(cfg))
        elif parsed.path == "/api/territory":
            self._json(200, read_territory_view(cfg))
        elif parsed.path == "/api/forts":
            self._json(200, read_forts_view(cfg))
        elif parsed.path == "/api/intel":
            self._json(200, read_intel(cfg))
        elif parsed.path == "/api/errors":
            self._json(200, read_errors(cfg))
        elif parsed.path == "/api/agent/status":
            self._json(200, self.server.supervisor.status())
        elif parsed.path.startswith("/static/"):
            code, ctype, body = serve_static(parsed.path[len("/static/"):])
            self._send(code, body, ctype)
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        cfg = self.server.cfg
        if parsed.path.startswith("/api/agent/"):
            action = parsed.path[len("/api/agent/"):]
            sup = self.server.supervisor
            fn = {"start": sup.start, "stop": sup.stop,
                  "pause": sup.pause, "resume": sup.resume}.get(action)
            if fn is None:
                self._json(404, {"ok": False, "error": "unknown agent action"})
                return
            try:  # drain and ignore any request body
                length = int(self.headers.get("Content-Length", "0"))
                if length:
                    self.rfile.read(length)
            except (ValueError, TypeError):
                pass
            self._json(200, fn())
            return
        if parsed.path == "/api/forts/decide":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                idx = int(body["index"])
                decision = str(body.get("decision", ""))
            except (ValueError, TypeError, KeyError):
                self._json(400, {"ok": False, "error": "need index + decision"})
                return
            from nta_agent.runtime import fort_decisions
            fort_decisions.update(cfg.fort_decisions_path, idx, decision)
            self._json(200, recompute_forts(cfg))
            return
        if parsed.path == "/api/chat":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, TypeError):
                self._json(400, {"ok": False, "error": "bad json"})
                return
            msg = str(body.get("message", "")).strip()
            if not msg:
                self._json(400, {"ok": False, "error": "empty message"})
                return
            hist = getattr(self.server, "chat_history", [])
            out = handle_chat(cfg, msg, history=hist)
            self.server.chat_history = (hist + [{"role": "user", "content": msg}])[-6:]
            self._json(200 if out.get("ok") else 503, out)
            return
        if parsed.path == "/api/profile":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, TypeError):
                self._json(400, {"ok": False, "error": "bad json"})
                return

            def _ints(v):
                out = []
                for x in v if isinstance(v, list) else []:
                    try:
                        out.append(int(x))
                    except (TypeError, ValueError):
                        pass
                return out

            # Build the edit from what the panel actually sent. The BuildOrderPanel
            # posts {order, skip} at top level; other panels post a nested section
            # ({leveling:{...}}, {logistics:{...}}, ...). Previously this hardcoded
            # edits={build:{order,skip}} for EVERY post — so a leveling/logistics
            # save was dropped AND it wiped build.order/skip to empty.
            edits: dict = {}
            if "order" in body or "skip" in body:
                edits["build"] = {"order": _ints(body.get("order", [])),
                                  "skip": _ints(body.get("skip", []))}
            for key in ("build", "leveling", "logistics", "occupy", "army",
                        "revive", "forge", "notes"):
                if key in body:
                    edits[key] = body[key]
            self._json(200, handle_profile_edit(cfg, edits))
            return
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
