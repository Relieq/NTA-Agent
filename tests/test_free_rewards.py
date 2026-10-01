"""FreeRewards: the free extras the game hands out — lucky-wheel spins, free gold and free war
tokens (shop), newbie gift-pack daily rewards. Server-authoritative: the service only ASKS when
its own clock says a reward is due, learns the next time from the reply, and backs off on any
refusal. It never buys anything (no ingot spend, no ads, no purchases)."""
from __future__ import annotations

import json

from nta_agent.runtime.free_rewards import FreeRewards
from nta_agent.state.schema import GameState, User


class Acts:
    """Records calls; replies come from ``replies`` (a value or a callable per route)."""
    def __init__(self, replies=None):
        self.replies, self.calls = replies or {}, []

    def _go(self, name, *a):
        self.calls.append((name, *a))
        r = self.replies.get(name, {})
        r = r(*a) if callable(r) else r
        if isinstance(r, Exception):
            raise r
        return r

    def wheel_info(self):
        return self._go("wheel_info")

    def wheel_begin(self):
        return self._go("wheel_begin")

    def wheel_ret(self, ok=True):
        return self._go("wheel_ret", ok)

    def buy_free_gold(self):
        return self._go("buy_free_gold")

    def buy_free_war_token(self):
        return self._go("buy_free_war_token")

    def newbie_reward_info(self):
        return self._go("newbie_reward_info")

    def claim_newbie_reward(self, pid):
        return self._go("claim_newbie_reward", pid)


def _state(**user):
    st = GameState(source="api")
    st.user = User(uid="me", raw=user)
    return st


def _svc(tmp_path, acts, t, **kw):
    ev = []
    svc = FreeRewards(acts, tmp_path / "free.json", on_event=lambda k, d=None: ev.append((k, d)),
                      clock=lambda: t[0], check_every_s=0, **kw)
    return svc, ev


def _calls(acts, name):
    return [c for c in acts.calls if c[0] == name]


# ---- free gold / war token ------------------------------------------------------------------
def test_free_gold_is_taken_when_due_and_the_next_time_comes_from_the_reply(tmp_path):
    t = [1000.0]
    acts = Acts({"buy_free_gold": {"gold": 120, "buyFreeGoldSurplusTime": 3_600_000}})
    svc, ev = _svc(tmp_path, acts, t)
    st = _state()                                   # surplus absent = 0 = available now
    svc.tick(st)
    assert len(_calls(acts, "buy_free_gold")) == 1
    assert st.resources.gold == 120                 # the reply's gold is applied
    assert any(k == "free_gold" for k, _ in ev)
    t[0] += 1800                                    # half the cooldown: not yet
    svc.tick(st)
    assert len(_calls(acts, "buy_free_gold")) == 1
    t[0] += 1801                                    # past it: again
    svc.tick(st)
    assert len(_calls(acts, "buy_free_gold")) == 2


def test_the_login_surplus_time_is_respected(tmp_path):
    t = [1000.0]
    acts = Acts({"buy_free_gold": {"gold": 5, "buyFreeGoldSurplusTime": 60_000}})
    svc, _ = _svc(tmp_path, acts, t)
    st = _state(buyFreeGoldSurplusTime=600_000, buyFreeWarTokenSurplusTime=600_000)
    svc.tick(st)
    assert _calls(acts, "buy_free_gold") == [] and _calls(acts, "buy_free_war_token") == []
    t[0] += 601
    svc.tick(st)
    assert len(_calls(acts, "buy_free_gold")) == 1 and len(_calls(acts, "buy_free_war_token")) == 1


def test_a_refusal_backs_off_and_a_missing_cooldown_never_loops(tmp_path):
    t = [1000.0]
    acts = Acts({"buy_free_gold": RuntimeError("lobby/HD_BuyFreeGold: ecode.123"),
                 "buy_free_war_token": {"warToken": 3}})      # no surplus time in the reply
    svc, ev = _svc(tmp_path, acts, t)
    st = _state()
    for _ in range(5):
        svc.tick(st)
    assert len(_calls(acts, "buy_free_gold")) == 1 and len(_calls(acts, "buy_free_war_token")) == 1
    assert any(k == "free_reward_error" for k, _ in ev)
    t[0] += 3601                                              # the back-off (1 h) is over
    svc.tick(st)
    assert len(_calls(acts, "buy_free_gold")) == 2


# ---- the lucky wheel ------------------------------------------------------------------------
def test_wheel_spins_when_the_free_spin_is_ready_and_applies_the_rewards(tmp_path):
    t = [1000.0]
    acts = Acts({
        "wheel_info": {"info": {"wheelResidueCount": 3, "wheelCurrCount": 1}},
        "wheel_begin": {"info": {}},                                   # no wait time -> spin
        "wheel_ret": {"id": 4, "info": {"wheelWaitTime": 1_800_000},
                      "rewards": {"cereal": {"count": 50}}}})
    svc, ev = _svc(tmp_path, acts, t)
    st = _state()
    svc.tick(st)
    assert [c[0] for c in acts.calls if c[0].startswith("wheel")] == [
        "wheel_info", "wheel_begin", "wheel_ret"]
    assert _calls(acts, "wheel_ret")[0][1] is True
    assert any(k == "free_wheel" for k, _ in ev)
    n = len(acts.calls)
    t[0] += 60                                                         # CD 30 min: not again yet
    svc.tick(st)
    assert len([c for c in acts.calls if c[0].startswith("wheel")]) == 3 and len(acts.calls) >= n


def test_wheel_waits_when_the_server_says_the_cooldown_is_running(tmp_path):
    t = [1000.0]
    acts = Acts({"wheel_info": {"info": {"wheelResidueCount": 2, "wheelWaitTime": 900_000}},
                 "wheel_begin": {"info": {"wheelWaitTime": 900_000}}})
    svc, _ = _svc(tmp_path, acts, t)
    svc.tick(_state())
    assert _calls(acts, "wheel_begin") == [] and _calls(acts, "wheel_ret") == []   # info said wait
    t[0] += 901
    svc.tick(_state())
    assert len(_calls(acts, "wheel_begin")) == 1
    assert _calls(acts, "wheel_ret") == []              # begin answered 'still cooling down'


def test_wheel_does_nothing_when_no_spin_is_left(tmp_path):
    t = [1000.0]
    acts = Acts({"wheel_info": {"info": {"wheelResidueCount": 0, "wheelCurrCount": 10}}})
    svc, _ = _svc(tmp_path, acts, t)
    svc.tick(_state())
    assert _calls(acts, "wheel_begin") == []


# ---- newbie gift pack -----------------------------------------------------------------------
def test_newbie_pack_days_are_claimed_when_due(tmp_path):
    t = [1000.0]
    acts = Acts({"newbie_reward_info": {"list": [
        {"productId": "pk1", "claimedDays": 2, "nextSurplusTime": 0},
        {"productId": "pk2", "claimedDays": 1, "nextSurplusTime": 5_000_000}]},
        "claim_newbie_reward": {"claimedDays": 3, "nextSurplusTime": 86_400_000}})
    svc, ev = _svc(tmp_path, acts, t)
    svc.tick(_state())
    assert _calls(acts, "claim_newbie_reward") == [("claim_newbie_reward", "pk1")]
    assert any(k == "free_newbie_pack" for k, _ in ev)


# ---- safety + persistence -------------------------------------------------------------------
def test_one_failing_reward_never_blocks_the_others_and_nothing_raises(tmp_path):
    t = [1000.0]
    acts = Acts({"wheel_info": RuntimeError("boom"),
                 "buy_free_gold": {"gold": 1, "buyFreeGoldSurplusTime": 1000},
                 "newbie_reward_info": RuntimeError("boom2")})
    svc, ev = _svc(tmp_path, acts, t)
    svc.tick(_state())
    assert len(_calls(acts, "buy_free_gold")) == 1
    assert sum(1 for k, _ in ev if k == "free_reward_error") >= 2


def test_the_schedule_survives_a_restart_and_is_written_for_the_dashboard(tmp_path):
    t = [1000.0]
    acts = Acts({"buy_free_gold": {"gold": 9, "buyFreeGoldSurplusTime": 7_200_000}})
    svc, _ = _svc(tmp_path, acts, t)
    svc.tick(_state())
    saved = json.loads((tmp_path / "free.json").read_text(encoding="utf-8"))
    assert saved["next"]["gold"] == 1000.0 + 7200 and saved["claimed"]["gold"] == 1
    acts2 = Acts({"buy_free_gold": {"gold": 9, "buyFreeGoldSurplusTime": 7_200_000}})
    svc2, _ = _svc(tmp_path, acts2, [2000.0])
    svc2.tick(_state())                                    # a new process, 1000 s later
    assert _calls(acts2, "buy_free_gold") == []            # still cooling down


def test_the_login_time_is_not_a_clock_for_a_stale_surplus(tmp_path):
    # the login surplus is a duration from the LOGIN; after a restart the new login carries a
    # fresh surplus: it must override the saved schedule, not be added to an old one
    t = [1000.0]
    acts = Acts({"buy_free_gold": {"gold": 1, "buyFreeGoldSurplusTime": 3_600_000}})
    svc, _ = _svc(tmp_path, acts, t)
    svc.tick(_state())
    acts2 = Acts({"buy_free_gold": {"gold": 1, "buyFreeGoldSurplusTime": 3_600_000}})
    svc2, _ = _svc(tmp_path, acts2, [1500.0])
    svc2.tick(_state(buyFreeGoldSurplusTime=100_000))      # the server now says: in 100 s
    assert _calls(acts2, "buy_free_gold") == []
    svc2.clock = lambda: 1601.0
    svc2.tick(_state(buyFreeGoldSurplusTime=100_000))
    assert len(_calls(acts2, "buy_free_gold")) == 1


# ---- plumbing: routes exist in the schema, the actions send the right params, the view reads --
def test_the_lobby_routes_and_their_messages_exist_in_the_schema():
    from nta_agent.io.api.protocol import Codec
    c = Codec.load()
    for route in ("lobby/HD_GetWheelInfo", "lobby/HD_WheelBegin", "lobby/HD_GetWheelRet",
                  "lobby/HD_BuyFreeGold", "lobby/HD_BuyFreeWarToken",
                  "lobby/HD_GetNewbieRewardInfo", "lobby/HD_ClaimNewbieReward"):
        msg = route.replace("/", "_").upper()
        assert c.has(msg + "_C2S") and c.has(msg + "_S2C"), route
    # the wheel result round-trips through the codec like a real reply would
    body = c.encode("LOBBY_HD_GETWHEELRET_C2S", {"ok": True})
    assert body
    assert c.encode("LOBBY_HD_CLAIMNEWBIEREWARD_C2S", {"productId": "pk1"})


def test_actions_send_the_documented_routes_and_never_the_paid_ones():
    from nta_agent.execution.actions import Actions

    class Sess:
        def __init__(self):
            self.sent = []
            self.state = GameState()

        def request(self, route, params=None, timeout=15):
            self.sent.append((route, params))
            return {}
    s = Sess()
    a = Actions(s)
    a.wheel_info(), a.wheel_begin(), a.wheel_ret(True), a.buy_free_gold()
    a.buy_free_war_token(), a.newbie_reward_info(), a.claim_newbie_reward("pk1")
    assert s.sent == [("lobby/HD_GetWheelInfo", {}), ("lobby/HD_WheelBegin", {}),
                      ("lobby/HD_GetWheelRet", {"ok": True}), ("lobby/HD_BuyFreeGold", {}),
                      ("lobby/HD_BuyFreeWarToken", {}), ("lobby/HD_GetNewbieRewardInfo", {}),
                      ("lobby/HD_ClaimNewbieReward", {"productId": "pk1"})]
    assert not any("NoCd" in r or "Forecast" in r for r, _ in s.sent)   # nothing that costs ingots


def test_the_dashboard_reads_the_schedule(tmp_path):
    from nta_agent.dashboard.server import read_free_rewards
    from nta_agent.runtime.config import RuntimeConfig
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)
    assert read_free_rewards(cfg) == {"next": {}, "claimed": {}, "last": {}}
    cfg.free_rewards_path.write_text(json.dumps({"next": {"gold": 5}, "claimed": {"gold": 2}}),
                                     encoding="utf-8")
    v = read_free_rewards(cfg)
    assert v["next"] == {"gold": 5} and v["claimed"] == {"gold": 2}
