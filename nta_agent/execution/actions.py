"""High-level game actions — the "hands" translate intents into API calls.

Each method wraps one or more ``_C2S`` requests behind a typed, verified call and
keeps :class:`GameState` in step with the result. Higher layers (rules, brain)
call these; they never touch the codec or MQTT client directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nta_agent.io.api.session import GameSession


@dataclass
class Actions:
    session: GameSession

    @property
    def _state(self):
        return self.session.state

    def _player(self) -> dict[str, Any]:
        raw = self._state.raw or {}
        return raw.get("player") or {}

    def main_city_index(self) -> int:
        """The player's main city index (from the live Entry rst)."""
        idx = self._player().get("mainCityIndex")
        if idx:
            return int(idx)
        mc = self._state.main_city
        return mc.index if mc else 0

    # ---- resource economy ------------------------------------------------ #
    def collect_city_output(self, index: int | None = None) -> dict:
        """Claim accumulated output from a city (default: the main city).

        Safe and beneficial: gathers the player's own produced resources.
        Returns the decoded ``UpdateOutPut`` rewards.
        """
        idx = index if index is not None else self.main_city_index()
        if not idx:
            raise ValueError("no city index to collect from")
        reply = self.session.request("game/HD_ClaimCityOutput", {"index": int(idx)})
        return reply.get("rewards", {})

    # ---- construction ---------------------------------------------------- #
    def upgrade_build(self, index: int, uid: str = "") -> dict:
        """Upgrade the building at a tile index (GAME_HD_UPAREABUILD)."""
        params = {"index": int(index)}
        if uid:
            params["uid"] = uid
        return self.session.request("game/HD_UpAreaBuild", params)

    # ---- reads ----------------------------------------------------------- #
    def get_area(self, index: int, no_record: bool = True) -> dict:
        return self.session.request(
            "game/HD_GetAreaInfo", {"index": int(index), "noRecord": no_record}
        )

    def get_marches(self) -> dict:
        return self.session.request("game/HD_GetMarchs", {})
