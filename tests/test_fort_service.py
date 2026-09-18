"""FortService: throttled scan on landCount change; writes forts.json."""
import json

from nta_agent.runtime.fort_service import FortService
from nta_agent.state.schema import GameState, User


def _state(land_count, main=100 * 600 + 100, uid="u1", forts=None):
    st = GameState(source="api")
    st.user = User(uid=uid)
    st.main_city_index = main
    st.raw = {"player": {
        "mainCityIndex": main,
        "landCount": land_count,
        "fortAutoSupports": forts or [],
    }}
    return st


class Cfg:
    forts_path = None
    fort_decisions_path = None


def _make(tmp_path, **kw):
    cfg = Cfg()
    cfg.forts_path = tmp_path / "forts.json"
    cfg.fort_decisions_path = tmp_path / "fort_decisions.json"
    return cfg, FortService(cfg=cfg, actions=object(), **kw)


def test_scans_and_writes_on_first_tick(tmp_path):
    owned = {100 * 600 + 100, 120 * 600 + 100}

    def scan(actions, main, uid, map_width=600, focus=None):
        return {"owned": set(owned), "cities": {}, "enemy_cells": {120 * 600 + 130},
                "enemy_cities": {120 * 600 + 130: 1}, "frontier": {100 * 600 + 101}}

    cfg, svc = _make(tmp_path, scan=scan, max_count_fn=lambda bid: 2)
    svc.tick(_state(land_count=2))
    data = json.loads(cfg.forts_path.read_text(encoding="utf-8"))
    assert data["owned_count"] == 2
    assert len(data["recommendations"]) == 1
    assert data["recommendations"][0]["index"] == 120 * 600 + 100
    # owned cells written as [x, y] pairs for the dashboard map
    assert [100, 100] in data["owned_cells"]
    assert [100, 120] in data["owned_cells"]
    assert len(data["owned_cells"]) == 2
    # enemy + frontier layers written too
    assert [130, 120] in data["enemy_cells"]
    assert {"x": 130, "y": 120, "type": 1} in data["enemy_cities"]
    assert [101, 100] in data["frontier"]


def test_skips_when_land_count_unchanged(tmp_path):
    calls = []

    def scan(actions, main, uid, map_width=600, focus=None):
        calls.append(1)
        return {"owned": {100 * 600 + 100}, "cities": {}, "enemy_cells": set(), "enemy_cities": {}, "frontier": set()}

    _cfg, svc = _make(tmp_path, scan=scan, max_count_fn=lambda bid: 2)
    st = _state(land_count=5)
    svc.tick(st)
    svc.tick(st)  # same landCount -> no re-scan
    assert len(calls) == 1


def test_rescans_when_land_count_changes(tmp_path):
    calls = []

    def scan(actions, main, uid, map_width=600, focus=None):
        calls.append(1)
        return {"owned": {100 * 600 + 100}, "cities": {}, "enemy_cells": set(), "enemy_cities": {}, "frontier": set()}

    _cfg, svc = _make(tmp_path, scan=scan, max_count_fn=lambda bid: 2)
    svc.tick(_state(land_count=5))
    svc.tick(_state(land_count=6))
    assert len(calls) == 2


def test_forts_json_respects_decisions(tmp_path):
    from nta_agent.runtime import fort_decisions as fd
    owned = {120 * 600 + 100, 100 * 600 + 120}

    def scan(actions, main, uid, map_width=600, focus=None):
        return {"owned": set(owned), "cities": {}, "enemy_cells": set(), "enemy_cities": {}, "frontier": set()}

    cfg, svc = _make(tmp_path, scan=scan, max_count_fn=lambda bid: 3)
    fd.update(cfg.fort_decisions_path, 120 * 600 + 100, "accept")
    fd.update(cfg.fort_decisions_path, 100 * 600 + 120, "reject")
    svc.tick(_state(land_count=2))
    data = json.loads(cfg.forts_path.read_text(encoding="utf-8"))
    rec_xy = [[r["x"], r["y"]] for r in data["recommendations"]]
    assert [100, 120] not in rec_xy           # accepted (idx 120*600+100) excluded
    assert [120, 100] not in rec_xy           # rejected (idx 100*600+120) excluded
    assert [100, 120] in data["accepted"]     # accepted listed
    assert [120, 100] in data["rejected"]     # rejected listed


def test_fort_cap_limits_recommendations(tmp_path):
    owned = {120 * 600 + 100, 100 * 600 + 120, 80 * 600 + 100}

    def scan(actions, main, uid, map_width=600, focus=None):
        return {"owned": set(owned), "cities": {}, "enemy_cells": set(), "enemy_cities": {}, "frontier": set()}

    # cap 2102 = 1, one fort already exists -> 0 slots -> no recs
    cfg, svc = _make(tmp_path, scan=scan, max_count_fn=lambda bid: 1)
    st = _state(land_count=3, forts=[{"index": 200 * 600 + 200, "val": 1}])
    svc.tick(st)
    data = json.loads(cfg.forts_path.read_text(encoding="utf-8"))
    assert data["recommendations"] == []


def test_writes_threats_and_alerts_on_incursion(tmp_path):
    # 2x2 owned block; an enemy cell adjacent to the east edge -> incursion.
    owned = {100 * 600 + 100, 100 * 600 + 101, 101 * 600 + 100, 101 * 600 + 101}

    def scan(actions, main, uid, map_width=600, focus=None):
        return {"owned": set(owned), "cities": {}, "enemy_cells": {100 * 600 + 102},
                "enemy_cities": {}, "frontier": set()}

    events = []
    cfg, svc = _make(tmp_path, scan=scan, max_count_fn=lambda bid: 2,
                     on_event=lambda k, d: events.append((k, d)))
    svc.tick(_state(land_count=4, main=100 * 600 + 100))
    data = json.loads(cfg.forts_path.read_text(encoding="utf-8"))
    assert data["threat_summary"]["count"] >= 1
    assert data["threats"][0]["adjacent"] is True
    assert any(k == "threat_alert" for k, d in events)
