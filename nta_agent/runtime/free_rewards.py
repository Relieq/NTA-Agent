"""Free extras the game hands out, claimed without the player: lucky-wheel spins, free gold and
free war tokens (shop), newbie gift-pack daily rewards.

All of them are server-authoritative lobby requests (``lobby/HD_...``): this service only ASKS when
its own clock says a reward is due, learns the next due time from the reply, and backs off on any
refusal. It NEVER buys anything — no ingot spend, no ads, no purchases (``BuyWheelNoCd``,
``BuyFreeForecast`` cost ingots and are deliberately not used). The schedule is saved in a small
JSON file (also read by the dashboard) so a restart does not ask again too early.

How each is judged (from the game client, ``index.js``):

* free gold / war token — ``isBuyLimitFree*``: ``now - getTime >= surplusTime``; the login user
  carries ``buyFreeGoldSurplusTime`` / ``buyFreeWarTokenSurplusTime`` (ms, absent = 0 = ready) and the
  claim's reply carries the next one;
* wheel — the client's ``checkCanWheel``: ``(wheelResidueCount > 0 || wheelCurrCount < 10) &&
  wait over``, i.e. 10 FREE spins a day (``wheelCurrCount`` = spins taken today) plus any extra
  spins left in ``wheelResidueCount``. ``HD_WheelBegin`` answers ``info.wheelWaitTime`` while it
  cools down, else the spin is on and ``HD_GetWheelRet {ok: true}`` returns the sector + rewards;
* newbie pack — ``HD_GetNewbieRewardInfo`` lists the packs; one whose ``nextSurplusTime`` has run
  out can be claimed with ``HD_ClaimNewbieReward {productId}``.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

NAMES = ("gold", "token", "wheel", "newbie")
WHEEL_DAILY_FREE = 10         # engine checkCanWheel: free spins per day (wheelCurrCount < 10)
WHEEL_RECHECK_S = 1800.0      # no spin left today / unknown: look again this often
NEWBIE_RECHECK_S = 6 * 3600.0


class FreeRewards:
    def __init__(self, actions, path, on_event=None, clock=None, check_every_s: float = 30.0,
                 error_backoff_s: float = 3600.0):
        self.actions = actions
        self.path = Path(path)
        self._on_event = on_event or (lambda *a: None)
        self.clock = clock or time.time
        self.check_every_s = check_every_s
        self.error_backoff_s = error_backoff_s
        d = self._load()
        self._d = {"next": dict(d.get("next") or {}), "claimed": dict(d.get("claimed") or {}),
                   "last": dict(d.get("last") or {})}
        self._seeded = False
        self._last_check = float("-inf")
        self._wheel_need_info = True
        self._newbie_skip: dict[str, float] = {}

    # ---- persistence -------------------------------------------------------------------
    def _load(self) -> dict:
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(self._d, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass

    # ---- bookkeeping -------------------------------------------------------------------
    def _event(self, kind: str, **detail) -> None:
        self._on_event(kind, detail)

    def _due(self, name: str, now: float) -> bool:
        return now >= float(self._d["next"].get(name, 0) or 0)

    def _schedule(self, name: str, at: float) -> None:
        self._d["next"][name] = float(at)

    def _claimed(self, name: str, now: float, **info) -> None:
        self._d["claimed"][name] = int(self._d["claimed"].get(name, 0)) + 1
        self._d["last"][name] = {"at": now, **info}

    @staticmethod
    def _ms(v) -> float:
        try:
            return max(float(v or 0), 0.0) / 1000.0
        except (TypeError, ValueError):
            return 0.0

    # ---- tick --------------------------------------------------------------------------
    def tick(self, state) -> None:
        now = self.clock()
        if now - self._last_check < self.check_every_s:
            return
        self._last_check = now
        if not self._seeded:
            self._seed(state, now)
        for name, fn in (("gold", self._free_gold), ("token", self._free_war_token),
                         ("wheel", self._wheel), ("newbie", self._newbie)):
            if not self._due(name, now):
                continue
            try:
                fn(state, now)
            except Exception as e:  # a failing reward never blocks the others nor the loop
                self._schedule(name, now + self.error_backoff_s)
                if name == "wheel":
                    self._wheel_need_info = True
                self._event("free_reward_error", reward=name, error=str(e)[:160])
        self._save()

    def _seed(self, state, now: float) -> None:
        """The fresh login's cooldowns beat the saved schedule (a surplus is a duration from the
        login). A key that is absent says nothing (protobuf drops 0, but we also keep the saved
        schedule so a stale fake / partial reply cannot make us ask early)."""
        self._seeded = True
        raw = getattr(getattr(state, "user", None), "raw", None) or {}
        for name, key in (("gold", "buyFreeGoldSurplusTime"), ("token", "buyFreeWarTokenSurplusTime")):
            if key in raw:
                self._schedule(name, now + self._ms(raw.get(key)))

    # ---- the rewards -------------------------------------------------------------------
    def _free_gold(self, state, now: float) -> None:
        r = self.actions.buy_free_gold() or {}
        if r.get("gold") is not None:
            state.resources.gold = int(r.get("gold") or 0)
        wait = self._ms(r.get("buyFreeGoldSurplusTime"))
        self._schedule("gold", now + (wait or self.error_backoff_s))   # no cooldown told: never loop
        self._claimed("gold", now, gold=r.get("gold"))
        self._event("free_gold", gold=r.get("gold"), next_in_s=round(wait))

    def _free_war_token(self, state, now: float) -> None:
        r = self.actions.buy_free_war_token() or {}
        wait = self._ms(r.get("buyFreeWarTokenSurplusTime"))
        self._schedule("token", now + (wait or self.error_backoff_s))
        self._claimed("token", now, war_token=r.get("warToken"))
        self._event("free_war_token", war_token=r.get("warToken"), next_in_s=round(wait))

    @staticmethod
    def _can_spin(info: dict) -> bool:
        """The client's rule: extra spins left, or fewer than 10 free spins taken today."""
        return (int(info.get("wheelResidueCount") or 0) > 0
                or int(info.get("wheelCurrCount") or 0) < WHEEL_DAILY_FREE)

    def _wheel(self, state, now: float) -> None:
        if self._wheel_need_info:
            info = (self.actions.wheel_info() or {}).get("info") or {}
            wait = self._ms(info.get("wheelWaitTime"))
            if not self._can_spin(info):                          # today's 10 free spins are used
                self._schedule("wheel", now + (wait or WHEEL_RECHECK_S))
                return
            self._wheel_need_info = False
            if wait > 0:                                          # a spin is left but cooling down
                self._schedule("wheel", now + wait + 1)
                return
        begun = (self.actions.wheel_begin() or {}).get("info") or {}
        wait = self._ms(begun.get("wheelWaitTime"))
        if wait > 0:                                              # still cooling down
            self._schedule("wheel", now + wait + 1)
            return
        ret = self.actions.wheel_ret(True) or {}                  # the spin itself (ok = true)
        if isinstance(ret.get("rewards"), dict):
            try:
                from nta_agent.state.store import apply_update_output
                apply_update_output(state, ret["rewards"])
            except Exception:
                pass
        recs = ret.get("wheelRecords") or []
        items = (recs[0].get("items") if recs and isinstance(recs[0], dict) else None) or []
        info = ret.get("info") or {}
        wait = self._ms(info.get("wheelWaitTime"))
        self._schedule("wheel", now + (wait + 1 if wait > 0 else 5))
        if info and not self._can_spin(info):          # that was the last spin of the day
            self._wheel_need_info = True
            self._schedule("wheel", now + max(wait, WHEEL_RECHECK_S))
        today = info.get("wheelCurrCount")
        self._claimed("wheel", now, sector=ret.get("id"), items=items, today=today)
        self._event("free_wheel", sector=ret.get("id"), items=items, next_in_s=round(wait),
                    today=today, extra_left=info.get("wheelResidueCount"))

    def _newbie(self, state, now: float) -> None:
        packs = (self.actions.newbie_reward_info() or {}).get("list") or []
        waits = []
        for p in packs:
            if not isinstance(p, dict) or not p.get("productId"):
                continue
            pid = str(p["productId"])
            wait = self._ms(p.get("nextSurplusTime"))
            if wait > 0:
                waits.append(wait)
                continue
            if self._newbie_skip.get(pid, 0) > now:
                continue
            try:
                r = self.actions.claim_newbie_reward(pid) or {}
            except Exception as e:      # e.g. every day of the pack already taken
                self._newbie_skip[pid] = now + 24 * 3600
                self._event("free_reward_error", reward="newbie", pack=pid, error=str(e)[:160])
                continue
            if isinstance(r.get("rewards"), dict):
                try:
                    from nta_agent.state.store import apply_update_output
                    apply_update_output(state, r["rewards"])
                except Exception:
                    pass
            nxt = self._ms(r.get("nextSurplusTime"))
            if nxt > 0:
                waits.append(nxt)
            self._claimed("newbie", now, pack=pid, days=r.get("claimedDays"))
            self._event("free_newbie_pack", pack=pid, days=r.get("claimedDays"),
                        items=r.get("items") or [])
        self._schedule("newbie", now + (min(waits) + 1 if waits else NEWBIE_RECHECK_S))
