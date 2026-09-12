import json
import threading
import urllib.error
import urllib.request

from nta_agent.dashboard.server import serve
from nta_agent.runtime.commands import read_pending
from nta_agent.runtime.config import RuntimeConfig


def _cfg(tmp_path):
    return RuntimeConfig.from_env({"NTA_DISTINCT_ID": "x", "NTA_LOG_DIR": str(tmp_path)})


def _serve(cfg):
    srv = serve(cfg, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def _post(port, path, body):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                 data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_get_decisions(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.decisions_path.write_text(json.dumps([{"track": "pawn", "lv": 1, "options": []}]))
    srv, port = _serve(cfg)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/decisions", timeout=5) as r:
            data = json.loads(r.read())
        assert data[0]["track"] == "pawn"
    finally:
        srv.shutdown()


def test_post_command_appends(tmp_path):
    cfg = _cfg(tmp_path)
    srv, port = _serve(cfg)
    try:
        st, body = _post(port, "/api/command",
                         {"action": "select", "track": "pawn", "lv": 1, "ceri_id": 5})
        assert st == 200 and body["ok"] is True and body["id"]
        pend = read_pending(cfg.commands_path, cfg.commands_done_path)
        assert pend[0]["action"] == "select" and pend[0]["ceri_id"] == 5
    finally:
        srv.shutdown()


def test_post_command_bad_body_400(tmp_path):
    cfg = _cfg(tmp_path)
    srv, port = _serve(cfg)
    try:
        st, body = _post(port, "/api/command", {"action": "nope", "track": "pawn", "lv": 1})
        assert st == 400 and body["ok"] is False
    finally:
        srv.shutdown()
