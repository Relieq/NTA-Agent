"""Enter the match and perform a first safe write action: collect city output."""
from __future__ import annotations

import json
import time
from pathlib import Path

from nta_agent.execution import Actions
from nta_agent.io.api.client import ApiError, ServerConfig
from nta_agent.io.api.session import GameSession

TF = Path(__file__).resolve().parent.parent / "build" / "nta_token.txt"
DISTINCT = "9b6bd157-ce26-481b-bcfd-1dc0829d7df8"


def main():
    s = GameSession(server=ServerConfig(host="nine-hk.twomiles.cn"))
    s.connect(timeout=15)
    login = s.login(TF.read_text().strip(), DISTINCT)
    if login.get("accountToken"):
        TF.write_text(login["accountToken"])
    s.enter_game(distinct_id=DISTINCT)
    act = Actions(s)
    r = s.state.resources
    print(f"before: cereal={r.cereal} timber={r.timber} stone={r.stone} | mainCity={act.main_city_index()}")
    try:
        rewards = act.collect_city_output()
        print("collect_city_output rewards keys:", list(rewards.keys()))
        for k in ("cereal", "timber", "stone", "granaryCap", "warehouseCap"):
            if k in rewards:
                print(f"   {k} =", json.dumps(rewards[k], default=str)[:80])
    except ApiError as e:
        print("collect ERROR (pipeline OK):", e)
    time.sleep(1.5)
    print("pushes:", [(p.route, p.msg_type) for p in s.drain_pushes()][:6])
    s.close()


if __name__ == "__main__":
    main()
