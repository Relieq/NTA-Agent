"""AlertService: capture + incoming hostile marches + approach -> alerts.json + events."""
import json
from types import SimpleNamespace

from nta_agent.runtime.alert_service import AlertService

ME = "me"
MAIN = 544 * 600 + 79


def _state(player=None, marches=None):
    return SimpleNamespace(raw={"player": player or {}}, user=SimpleNamespace(uid=ME),
                           main_city_index=MAIN, world_marches=marches or {})


class Acts:
    def __init__(self, marches):
        self.calls = 0
        self._m = marches
    def get_marches(self):
        self.calls += 1
        return {"list": self._m}


def _cfg(tmp_path):
    return SimpleNamespace(alerts_path=tmp_path / "alerts.json",
                           forts_path=tmp_path / "forts.json")


def test_polls_marches_and_alerts_incoming_once(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.forts_path.write_text(json.dumps({"owned_cells": [], "approach": {"near_count": 0}}),
                              encoding="utf-8")
    enemy = {"uid": "m1", "owner": "36781907", "targetIndex": MAIN, "targetIsCity": True,
             "startIndex": MAIN + 600 * 9, "surplusTime": 90000, "armyName": "x"}
    acts = Acts([enemy])
    events = []
    svc = AlertService(cfg, acts, on_event=lambda k, d: events.append((k, d)),
                       poll_every=3, clock=lambda: 50.0)
    st = _state()
    svc.tick(st)                               # first tick polls
    svc.tick(st)
    assert acts.calls == 1                     # throttled
    out = json.loads(cfg.alerts_path.read_text(encoding="utf-8"))
    assert out["captured"] is None
    assert [h["uid"] for h in out["incoming"]] == ["m1"]
    assert out["incoming"][0]["target_is_main"] is True
    assert [k for k, _ in events] == ["incoming_attack"]   # once per march, not per tick
    assert out["level"] == "danger"


def test_captured_is_top_level_alert(tmp_path):
    cfg = _cfg(tmp_path)
    svc = AlertService(cfg, Acts([]), poll_every=99, clock=lambda: 1.0)
    svc.tick(_state(player={"captureInfo": {"uid": "36781907", "time": 5}}))
    out = json.loads(cfg.alerts_path.read_text(encoding="utf-8"))
    assert out["captured"]["uid"] == "36781907"
    assert out["level"] == "captured"


def test_quiet_when_nothing(tmp_path):
    cfg = _cfg(tmp_path)
    svc = AlertService(cfg, Acts([]), poll_every=1, clock=lambda: 1.0)
    svc.tick(_state())
    out = json.loads(cfg.alerts_path.read_text(encoding="utf-8"))
    assert out["level"] == "ok" and out["incoming"] == []
