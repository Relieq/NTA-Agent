"""Alliance members = allies (joined 2026-09-26): not enemies anywhere."""
from __future__ import annotations

from types import SimpleNamespace

from nta_agent.execution.alerts import hostile_marches
from nta_agent.execution.alliance import AllyCache


class Acts:
    def __init__(self):
        self.calls = 0

    def get_alliance(self, uid):
        self.calls += 1
        return {"uid": uid, "members": [{"uid": "me"}, {"uid": "a1"}, {"uid": "a2"}]}


def _state(alli="ALLI1"):
    return SimpleNamespace(user=SimpleNamespace(uid="me"),
                           raw={"player": {"allianceUid": alli}})


def test_members_minus_me_cached():
    t = [1000.0]
    cache = AllyCache(ttl_s=600, clock=lambda: t[0])
    acts = Acts()
    assert cache.uids(acts, _state()) == {"a1", "a2"}
    cache.uids(acts, _state())
    assert acts.calls == 1                       # cached
    t[0] += 601
    cache.uids(acts, _state())
    assert acts.calls == 2                       # refreshed after the TTL


def test_no_alliance_no_allies():
    acts = Acts()
    assert AllyCache().uids(acts, _state(alli="")) == set()
    assert acts.calls == 0


def test_fetch_failure_keeps_the_last_known_allies():
    cache = AllyCache(ttl_s=0)
    acts = Acts()
    assert cache.uids(acts, _state()) == {"a1", "a2"}

    def boom(uid):
        raise RuntimeError("down")
    acts.get_alliance = boom
    assert cache.uids(acts, _state()) == {"a1", "a2"}


def test_allied_marches_are_not_hostile():
    marches = {"m1": {"uid": "m1", "owner": "a1", "targetIndex": 5, "surplusTime": 1000},
               "m2": {"uid": "m2", "owner": "x9", "targetIndex": 5, "surplusTime": 1000}}
    out = hostile_marches(marches, "me", {5}, 0, allies={"a1"}, now=0)
    assert [m["owner"] for m in out] == ["x9"]
