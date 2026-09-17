import json
import threading
import urllib.error
import urllib.request

from nta_agent.dashboard.server import serve
from nta_agent.runtime.config import RuntimeConfig


class FakeSup:
    def __init__(self): self.calls = []
    def status(self): return {"engine": "STOPPED", "pid": None, "uptime": 0.0}
    def start(self): self.calls.append("start"); return {"engine": "RUNNING", "pid": 1, "uptime": 0.0}
    def stop(self): self.calls.append("stop"); return {"engine": "STOPPED", "pid": None, "uptime": 0.0}
    def pause(self): self.calls.append("pause"); return {"engine": "PAUSED", "pid": 1, "uptime": 1.0}
    def resume(self): self.calls.append("resume"); return {"engine": "RUNNING", "pid": 1, "uptime": 2.0}


def _cfg(tmp_path):
    return RuntimeConfig.from_env({"NTA_DISTINCT_ID": "x", "NTA_LOG_DIR": str(tmp_path)})


def _serve(tmp_path):
    srv = serve(_cfg(tmp_path), 0)
    srv.supervisor = FakeSup()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
        return json.loads(r.read())


def _post(port, path):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=b"{}",
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def test_status_endpoint(tmp_path):
    srv = _serve(tmp_path)
    try:
        assert _get(srv.server_address[1], "/api/agent/status")["engine"] == "STOPPED"
    finally:
        srv.shutdown()


def test_action_endpoints(tmp_path):
    srv = _serve(tmp_path)
    port = srv.server_address[1]
    try:
        for action, engine in (("start", "RUNNING"), ("pause", "PAUSED"),
                               ("resume", "RUNNING"), ("stop", "STOPPED")):
            assert _post(port, f"/api/agent/{action}")["engine"] == engine
        assert srv.supervisor.calls == ["start", "pause", "resume", "stop"]
    finally:
        srv.shutdown()


def test_unknown_agent_action_404(tmp_path):
    srv = _serve(tmp_path)
    try:
        try:
            _post(srv.server_address[1], "/api/agent/frobnicate")
            assert False, "expected HTTP 404"
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        srv.shutdown()
