import json
import threading
import urllib.request

from nta_agent.brain.lessons import LessonStore
from nta_agent.dashboard.server import serve
from nta_agent.execution.ledger import FailureLedger
from nta_agent.runtime.config import RuntimeConfig


def _cfg(tmp_path):
    return RuntimeConfig.from_env({"NTA_DISTINCT_ID": "x", "NTA_LOG_DIR": str(tmp_path)})


def _serve(cfg):
    srv = serve(cfg, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
        return json.loads(r.read())


def _post(port, path, payload):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def test_failures_and_lessons_endpoints(tmp_path):
    cfg = _cfg(tmp_path)
    led = FailureLedger(cfg.failures_path)
    led.record("battle_loss", {"self_dead": 1, "counterfactual": {"best_order": "tank_first"}})
    store = LessonStore(cfg.lessons_path)
    lid = store.upsert({"trigger": {"kind": "battle_loss"}, "diagnosis": "AoE",
                        "resolution": {"advice": "bring more tanks"}, "evidence": ["e1"]})
    srv = _serve(cfg)
    port = srv.server_address[1]
    try:
        assert _get(port, "/api/failures")["failures"][0]["kind"] == "battle_loss"
        assert _get(port, "/api/lessons")["lessons"][0]["id"] == lid
        # retire hides it from active view in the store
        _post(port, "/api/lessons/retire", {"id": lid})
        assert LessonStore(cfg.lessons_path).active() == []
    finally:
        srv.shutdown()


def test_failures_endpoint_empty_when_no_file(tmp_path):
    srv = _serve(_cfg(tmp_path))
    try:
        assert _get(srv.server_address[1], "/api/failures") == {"failures": []}
        assert _get(srv.server_address[1], "/api/lessons") == {"lessons": []}
    finally:
        srv.shutdown()
