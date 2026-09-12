import json
import threading
import urllib.request

from nta_agent.dashboard.server import serve
from nta_agent.runtime.config import RuntimeConfig


def _cfg(tmp_path):
    return RuntimeConfig.from_env({"NTA_DISTINCT_ID": "x", "NTA_LOG_DIR": str(tmp_path)})


def test_get_armies(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.armies_path.write_text(json.dumps([{"uid": "a1", "name": "Đội 1", "pawns": []}]))
    srv = serve(cfg, 0)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/armies", timeout=5) as r:
            data = json.loads(r.read())
        assert data[0]["name"] == "Đội 1"
    finally:
        srv.shutdown()
