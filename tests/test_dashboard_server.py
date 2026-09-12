import json
import threading
import urllib.request

from nta_agent.dashboard.server import serve
from nta_agent.runtime.config import RuntimeConfig


def _cfg(tmp_path):
    return RuntimeConfig.from_env({"NTA_DISTINCT_ID": "x", "NTA_LOG_DIR": str(tmp_path)})


def _run(srv):
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return t


def _get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
        return r.status, r.read().decode("utf-8")


def test_index_and_apis(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.snapshot_path.write_text(json.dumps(
        {"main_city_index": 5, "resources": {"cereal": 9},
         "builds": [{"index": 5, "id": 2001, "lv": 2, "uid": "b1"}]}))
    cfg.event_log_path.write_text(json.dumps({"kind": "tick", "i": 0}) + "\n")
    srv = serve(cfg, 0)
    port = srv.server_address[1]
    _run(srv)
    try:
        st, body = _get(port, "/")
        assert st == 200 and "NTA Agent" in body
        st, body = _get(port, "/api/state")
        d = json.loads(body)
        assert st == 200 and d["ok"] is True
        assert d["builds"][0]["name"]  # enriched with a name (VN or #id)
        st, body = _get(port, "/api/events?n=2")
        assert st == 200 and isinstance(json.loads(body), list)
    finally:
        srv.shutdown()


def test_state_waiting_when_missing(tmp_path):
    cfg = _cfg(tmp_path)
    srv = serve(cfg, 0)
    port = srv.server_address[1]
    _run(srv)
    try:
        _, body = _get(port, "/api/state")
        assert json.loads(body) == {"ok": False}
    finally:
        srv.shutdown()
