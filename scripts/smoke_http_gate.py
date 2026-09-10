"""Verify the read-only HTTP bootstrap endpoints."""
import json
from nta_agent.io.api.http_gate import HttpGate

g = HttpGate("nine-hk.twomiles.cn")
for path, data in [("/getServerInfo", {}), ("/getNotice", {"lang": "vi"})]:
    try:
        res = g.post(path, data)
        s = json.dumps(res, ensure_ascii=False, default=str) if isinstance(res, (dict, list)) else str(res)
        print(f"[{path}] -> {s[:400]}")
    except Exception as e:
        print(f"[{path}] FAILED: {type(e).__name__}: {e}")
