"""Allies = the other members of the player's alliance (never treated as enemies).

The player's alliance uid comes from the entry (``player.allianceUid``); its
members from ``HD_GetAlliance{uid}``. Cached with a TTL; a failed fetch keeps the
last known members so a hiccup never turns allies back into 'enemies'.
"""
from __future__ import annotations

import time


class AllyCache:
    def __init__(self, ttl_s: float = 600.0, clock=None):
        self.ttl_s = ttl_s
        self._clock = clock or time.time
        self._alli = None
        self._uids: set[str] = set()
        self._at = None

    def uids(self, actions, state) -> set[str]:
        player = (getattr(state, "raw", None) or {}).get("player") or {}
        alli = str(player.get("allianceUid") or "")
        if not alli:
            self._alli, self._uids, self._at = None, set(), None
            return set()
        now = self._clock()
        if alli == self._alli and self._at is not None and now - self._at < self.ttl_s:
            return set(self._uids)
        me = str(getattr(getattr(state, "user", None), "uid", "") or "")
        try:
            info = actions.get_alliance(alli) or {}
            self._uids = {str(m.get("uid")) for m in info.get("members") or []
                          if isinstance(m, dict) and m.get("uid") and str(m.get("uid")) != me}
            self._alli, self._at = alli, now
        except Exception:
            pass  # keep the last known members
        return set(self._uids)


_DEFAULT = AllyCache()


def ally_uids(actions, state) -> set[str]:
    """The shared cache (FortService, DigService, OccupyCell, alerts)."""
    return _DEFAULT.uids(actions, state)
