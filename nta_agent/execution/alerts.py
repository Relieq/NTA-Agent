"""Early-warning signals the hands surface to the human (pure, no I/O).

- ``capture_info``: our main city has fallen (engine ``isCapture``: player
  ``captureInfo`` set by ENTRY or the world ``CAPTURE`` notify). While captured
  the agent must not act — the player chooses re-create / settle / wait.
- ``hostile_marches``: another player's march heading for our main city or one
  of our cells (world ``ADD_MARCH`` notifies / ``HD_GetMarchs``). This is the
  earliest warning of a siege — before any battle starts.

The agent never fights back here: it only reports (agent = assistant).
"""
from __future__ import annotations

import time


def capture_info(state) -> dict | None:
    """The live captureInfo {uid: attacker, time} if our city is captured, else None."""
    player = ((getattr(state, "raw", None) or {}).get("player") or {})
    ci = player.get("captureInfo")
    if isinstance(ci, dict) and ci.get("uid"):
        return ci
    return None


def _main_block(main: int, mw: int) -> set[int]:
    return {main, main + 1, main + mw, main + mw + 1} if main else set()


def hostile_marches(marches: dict, my_uid, owned, main: int, *, mw: int = 600,
                    now: float | None = None, allies=()) -> list[dict]:
    """Other players' marches targeting our main city block or an owned cell.

    Sorted most-dangerous first: strikes on the main city, then soonest arrival.
    ``eta_s`` = server surplusTime (ms) minus the time since we received it.
    """
    me = str(my_uid)
    allies = {str(a) for a in (allies or ())}
    block = _main_block(int(main or 0), mw)
    owned = set(owned or ())
    now = time.time() if now is None else now
    out = []
    for m in (marches or {}).values():
        if not isinstance(m, dict) or str(m.get("owner", "")) in ("", me):
            continue
        if str(m.get("owner", "")) in allies:  # an ally's march (e.g. support) isn't an attack
            continue
        tgt = int(m.get("targetIndex", 0) or 0)
        on_main = tgt in block
        if not (on_main or tgt in owned or str(m.get("targetUid", "")) == me):
            continue
        elapsed = max(0.0, now - float(m.get("_rx", now) or now))
        eta = max(0.0, float(m.get("surplusTime", 0) or 0) / 1000.0 - elapsed)
        out.append({"uid": str(m.get("uid", "")), "owner": str(m.get("owner", "")),
                    "army": m.get("armyName") or "", "target": tgt,
                    "target_xy": [tgt % mw, tgt // mw], "target_is_main": on_main,
                    "from_xy": [int(m.get("startIndex", 0) or 0) % mw,
                                int(m.get("startIndex", 0) or 0) // mw],
                    "eta_s": round(eta, 1)})
    out.sort(key=lambda h: (not h["target_is_main"], h["eta_s"]))
    return out
