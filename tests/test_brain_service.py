from types import SimpleNamespace

from nta_agent.brain.policies import BrainPolicy
from nta_agent.execution.profile import load_profile
from nta_agent.runtime.brain_service import BrainService

_RES = ("cereal", "timber", "stone", "iron", "gold", "stamina",
        "exp_book", "up_scroll", "fixator")


def _cfg(tmp_path):
    return SimpleNamespace(profile_path=tmp_path / "profile.json")


def _state():
    return SimpleNamespace(main_city_index=7,
                           resources=SimpleNamespace(**{k: 0 for k in _RES}), raw={})


def test_applies_sanitized_edits_in_place_and_emits(tmp_path):
    prof = load_profile("none")
    events = []
    actions = SimpleNamespace(get_player_armys=lambda: [{"uid": "A", "name": "D1", "pawns": []}])
    svc = BrainService(prof, _cfg(tmp_path), on_event=lambda k, d: events.append((k, d)),
                       actions=actions, policy=BrainPolicy(every_ticks=1, max_calls=5),
                       llm_propose=lambda dg, p: {"occupy": {"max_loss": 12},
                                                  "army": {"group": ["A"]}, "rationale": "tune"})
    svc.tick(_state())
    assert prof.occupy["max_loss"] == 12       # mutated in place
    assert prof.army["group"] == ["A"]
    assert any(k == "brain_plan" for k, d in events)
    assert (tmp_path / "profile.json").exists()  # persisted


def test_skips_off_cadence_and_survives_unavailable(tmp_path):
    from nta_agent.brain.llm import BrainUnavailable
    prof = load_profile("none")

    def boom(dg, p):
        raise BrainUnavailable("no key")

    svc = BrainService(prof, _cfg(tmp_path),
                       actions=SimpleNamespace(get_player_armys=list),
                       policy=BrainPolicy(every_ticks=10, max_calls=5), llm_propose=boom)
    svc.tick(_state())          # tick 1: off cadence -> no call, no raise
    for _ in range(9):
        svc.tick(_state())      # tick 10: fires but BrainUnavailable -> swallowed
    assert prof.occupy["max_loss"] == 0.0   # unchanged


def test_territory_summary_from_forts_json(tmp_path):
    import json
    fp = tmp_path / "forts.json"
    fp.write_text(json.dumps({
        "owned_count": 23, "enemy_cells": [[104, 100], [200, 200]],
        "enemy_cities": [{"x": 104, "y": 100, "type": 1}], "frontier": [[99, 100]],
        "recommendations": [],
    }), encoding="utf-8")
    cfg = SimpleNamespace(profile_path=tmp_path / "profile.json", forts_path=fp)
    svc = BrainService(load_profile("none"), cfg)
    st = SimpleNamespace(main_city_index=100 * 600 + 100)  # (100,100)
    terr = svc._territory(st)
    assert terr["owned"] == 23 and terr["enemy_cells"] == 2 and terr["frontier"] == 1
    assert terr["nearest_enemy_dist"] == 4  # (104,100) is 4 away


def test_territory_none_when_no_file(tmp_path):
    cfg = SimpleNamespace(profile_path=tmp_path / "p.json", forts_path=tmp_path / "missing.json")
    svc = BrainService(load_profile("none"), cfg)
    assert svc._territory(SimpleNamespace(main_city_index=1)) is None
