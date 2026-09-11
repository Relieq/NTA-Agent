"""Connect to the live game gate over MQTT/WebSocket/TLS and report.

    python scripts/smoke_api_connect.py --host nine-hk.twomiles.cn

Proves the transport (WS+TLS+MQTT CONNACK) end to end. Does NOT log in.
"""
from __future__ import annotations

import argparse
import time

from nta_agent.io.api.client import GameClient, ServerConfig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="nine-hk.twomiles.cn")
    ap.add_argument("--port", type=int, default=3653)
    ap.add_argument("--timeout", type=float, default=15)
    a = ap.parse_args()

    gc = GameClient(server=ServerConfig(host=a.host, port=a.port))
    print(f"clientId : {gc.client_id}")
    print(f"connecting to wss://{a.host}:{a.port}/mqtt ...")
    t0 = time.time()
    try:
        gc.connect(timeout=a.timeout)
        print(f"CONNECTED in {time.time()-t0:.2f}s  (MQTT CONNACK ok)")
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")
        return
    finally:
        pass
    time.sleep(1)
    gc.close()
    print("closed.")


if __name__ == "__main__":
    main()
