"""Log in, enter the newbie match, and print the resulting GameState (via API)."""
from __future__ import annotations
import argparse, time
from pathlib import Path
from nta_agent.io.api.session import GameSession
from nta_agent.io.api.client import ServerConfig

TOKEN_FILE = Path(__file__).resolve().parent.parent / "build" / "nta_token.txt"
DISTINCT = "9b6bd157-ce26-481b-bcfd-1dc0829d7df8"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="nine-hk.twomiles.cn")
    ap.add_argument("--token", default="")
    a = ap.parse_args()
    token = a.token or (TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else "")
    if not token:
        raise SystemExit("no token: pass --token or create %s" % TOKEN_FILE)

    s = GameSession(server=ServerConfig(host=a.host))
    s.connect(timeout=15)
    login = s.login(token, DISTINCT)
    if login.get("accountToken"):
        TOKEN_FILE.write_text(login["accountToken"])
    print(f"LOGIN uid={s.state.user.uid} nickname={s.state.user.nickname}")

    s.enter_game(distinct_id=DISTINCT)
    st = s.state
    r = st.resources
    print("== GameState (from API) ==")
    print(f"  user      : {st.user.uid} / {st.user.nickname}")
    print(f"  resources : cereal={r.cereal} timber={r.timber} stone={r.stone} stamina={r.stamina}")
    print(f"  heroes    : {[h.lv for h in st.heroes]}")
    print(f"  source    : {st.source}")
    print(f"  raw keys  : {list(st.raw.keys())}")

    time.sleep(2)
    pushes = s.drain_pushes()
    print(f"  pushes    : {[(p.route, p.msg_type) for p in pushes][:6]}")
    s.close()


if __name__ == "__main__":
    main()
