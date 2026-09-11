"""Send one request to the live gate and print the decoded reply.

    python scripts/smoke_api_request.py --route game/HD_GetMarchs

An UNAUTHENTICATED request (no login) is the safe way to prove the full
request -> reply -> S2C_RESULT decode pipeline without touching any account.
"""
from __future__ import annotations

import argparse
import json

from nta_agent.io.api.client import ApiError, GameClient, ServerConfig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="nine-hk.twomiles.cn")
    ap.add_argument("--route", default="game/HD_GetMarchs")
    ap.add_argument("--params", default="{}")
    ap.add_argument("--timeout", type=float, default=12)
    a = ap.parse_args()

    gc = GameClient(server=ServerConfig(host=a.host))
    gc.connect(timeout=15)
    print("connected:", gc.connected, "| clientId:", gc.client_id)
    try:
        reply = gc.request(a.route, json.loads(a.params), timeout=a.timeout)
        print("REPLY (decoded):", json.dumps(reply, ensure_ascii=False, default=str)[:800])
    except ApiError as e:
        print("SERVER ERROR (pipeline OK — decoded S2C_RESULT.error):", e)
    except TimeoutError as e:
        print("TIMEOUT (no reply):", e)
    finally:
        gc.close()


if __name__ == "__main__":
    main()
