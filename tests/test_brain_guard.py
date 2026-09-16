from nta_agent.brain.guard import sanitize_edits
from nta_agent.execution.profile import load_profile


def _prof():
    return load_profile("nonexistent")  # defaults


def test_clamps_occupy_and_drops_unknown():
    e = {"occupy": {"max_loss": 250, "max_march_ms": -5, "bogus": 1,
                    "loot": {"enabled": "yes", "min_reward_per_chest": -3}},
         "junk": 9}
    out = sanitize_edits(e, _prof(), set())
    assert out["occupy"]["max_loss"] == 100          # clamped to 100
    assert out["occupy"]["max_march_ms"] == 0        # clamped to >=0
    assert out["occupy"]["loot"]["enabled"] is True  # coerced bool
    assert out["occupy"]["loot"]["min_reward_per_chest"] == 0
    assert "bogus" not in out["occupy"] and "junk" not in out


def test_army_only_real_uids_and_nonneg_counts():
    e = {"army": {"group": ["A", "X"], "roles": {"A": "tank", "X": "archer", "A2": "bad"},
                  "onetile": 0, "composition": {"A": {"3101": -2, "3305": 3}, "X": {"3101": 1}}}}
    out = sanitize_edits(e, _prof(), {"A"})
    assert out["army"]["group"] == ["A"]             # X not real
    assert out["army"]["roles"] == {"A": "tank"}     # X not real, A2 not real
    assert out["army"]["onetile"] is False
    assert out["army"]["composition"] == {"A": {"3101": 0, "3305": 3}}  # X dropped, clamp >=0


def test_fully_invalid_is_empty():
    assert sanitize_edits({"nope": 1}, _prof(), set()) == {}
