"""Login via GameSession, observe server pushes, and read current game info."""
from __future__ import annotations
import argparse, json, time
from nta_agent.io.api.session import GameSession
from nta_agent.io.api.client import ServerConfig, ApiError


def dump(label, obj):
    print(label, json.dumps(obj, ensure_ascii=True, default=str)[:900])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="nine-hk.twomiles.cn")
    ap.add_argument("--token", required=True)
    ap.add_argument("--distinct-id", default="9b6bd157-ce26-481b-bcfd-1dc0829d7df8")
    ap.add_argument("--observe", type=float, default=6)
    a = ap.parse_args()

    s = GameSession(server=ServerConfig(host=a.host))
    s.connect(timeout=15)
    reply = s.login(a.token, a.distinct_id)
    u = s.state.user
    print(f"LOGIN OK  uid={u.uid} nickname={u.nickname}")

    print(f"observing pushes for {a.observe}s ...")
    time.sleep(a.observe)
    for p in s.drain_pushes():
        keys = list(p.data.keys()) if isinstance(p.data, dict) else p.data
        print(f"  PUSH {p.route}  type={p.msg_type or '-'}  keys={keys}")

    for route in ["lobby/HD_GetCurGameInfo", "lobby/HD_GetUserTotalGameCount"]:
        try:
            r = s.request(route, {}, timeout=10)
            dump(f"  {route} ->", r)
        except ApiError as e:
            print(f"  {route} ERROR: {e}")
        except TimeoutError as e:
            print(f"  {route} TIMEOUT: {e}")
    s.close()


if __name__ == "__main__":
    main()
