"""HTTP-level test for /api/profile POST routing (leveling & build independent)."""
import json
import threading
import urllib.request

from nta_agent.dashboard.server import serve
from nta_agent.runtime.config import RuntimeConfig


def _serve(tmp_path):
    srv = serve(RuntimeConfig.from_env({"NTA_DISTINCT_ID": "x", "NTA_LOG_DIR": str(tmp_path)}), 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _post(port, obj):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/profile",
                                 data=json.dumps(obj).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def _get(port):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/profile", timeout=5) as r:
        return json.loads(r.read())


def test_profile_post_leveling_persists_and_keeps_build(tmp_path):
    srv = _serve(tmp_path)
    port = srv.server_address[1]
    try:
        _post(port, {"order": [2016, 2006], "skip": [2000]})   # build (top-level)
        _post(port, {"leveling": {"enabled": True, "target_lv": 5, "max_leveling": 3}})
        v = _get(port)
        # leveling saved AND the build edit was NOT wiped by the leveling post
        assert v["leveling"] == {"enabled": True, "target_lv": 5, "max_leveling": 3}
        assert v["build"]["order"] == [2016, 2006] and v["build"]["skip"] == [2000]
    finally:
        srv.shutdown()
