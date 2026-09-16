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
