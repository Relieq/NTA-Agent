"""Authenticated round-trip: lobby/HD_TryLogin with a stored accountToken.

Prints the decoded LOBBY_HD_TRYLOGIN_S2C (real server user state). May kick an
active game session on the same account.
"""
from __future__ import annotations

import argparse
import json

from nta_agent.io.api.client import ApiError, GameClient, ServerConfig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="nine-hk.twomiles.cn")
    ap.add_argument("--token", required=True)
    ap.add_argument("--distinct-id", default="")
    ap.add_argument("--lang", default="vi")
    a = ap.parse_args()

    params = {
        "accountToken": a.token,
        "distinctId": a.distinct_id,
        "os": "Android 9",
        "lang": a.lang,
        "platform": "google",
        "version": "4.4.4",
    }
    gc = GameClient(server=ServerConfig(host=a.host))
    gc.connect(timeout=15)
    print("connected:", gc.connected)
    try:
        reply = gc.request("lobby/HD_TryLogin", params, timeout=15)
        user = reply.get("user", {})
        print("LOGIN OK. reply keys:", list(reply.keys()))
        print("  accountToken(new):", str(reply.get("accountToken"))[:24], "...")
        print("  user field count:", len(user) if isinstance(user, dict) else user)
        print("  user keys:", list(user.keys())[:40] if isinstance(user, dict) else user)
        print("  raw (trunc):", json.dumps(reply, ensure_ascii=True, default=str)[:600])
    except ApiError as e:
        print("SERVER ERROR (pipeline OK):", e)
    except TimeoutError as e:
        print("TIMEOUT:", e)
    finally:
        gc.close()


if __name__ == "__main__":
    main()
