"""Prove session recovery: connect, enter, force a drop, recover, verify state."""
from __future__ import annotations
from pathlib import Path
from nta_agent.io.api.session import GameSession
from nta_agent.io.api.client import ServerConfig

TF = Path(__file__).resolve().parent.parent / "build" / "nta_token.txt"
DISTINCT = "9b6bd157-ce26-481b-bcfd-1dc0829d7df8"


def main():
    s = GameSession(server=ServerConfig(host="nine-hk.twomiles.cn"), token_path=TF)
    s.connect(timeout=15)
    s.login(distinct_id=DISTINCT)
    s.enter_game(distinct_id=DISTINCT)
    print(f"entered: sid={s._sid} cereal={s.state.resources.cereal} connected={s.client.connected}")

    print("-- forcing a disconnect --")
    s.client.close()
    print(f"after close: connected={s.client.connected}")

    print("-- recover() --")
    s.recover()
    print(f"recovered: connected={s.client.connected} sid={s._sid} "
          f"cereal={s.state.resources.cereal} uid={s.state.user.uid}")
    s.close()


if __name__ == "__main__":
    main()
