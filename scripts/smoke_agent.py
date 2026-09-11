"""Run the agent loop for a few ticks against the live newbie match."""
from __future__ import annotations
from pathlib import Path
from nta_agent.io.api.session import GameSession
from nta_agent.io.api.client import ServerConfig
from nta_agent.execution import Agent

TF = Path(__file__).resolve().parent.parent / "build" / "nta_token.txt"
DISTINCT = "9b6bd157-ce26-481b-bcfd-1dc0829d7df8"


def main():
    s = GameSession(server=ServerConfig(host="nine-hk.twomiles.cn"), token_path=TF)
    s.connect(timeout=15)
    s.login(distinct_id=DISTINCT)          # reads+writes token via token_path
    s.enter_game(distinct_id=DISTINCT)
    agent = Agent(session=s)

    def on_tick(i, fired, state):
        r = state.resources
        print(f"tick {i}: fired={fired} | cereal={r.cereal} timber={r.timber} stone={r.stone}")

    agent.run(ticks=3, interval=4, on_tick=on_tick)
    s.close()


if __name__ == "__main__":
    main()
