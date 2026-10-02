from types import SimpleNamespace

from nta_agent.execution.claims import ArmyClaims
from nta_agent.runtime.claims_wiring import RULE_HOOKS, wire_claims


def _claims():
    c = ArmyClaims()
    c.register("pawn_moves", lambda: {"chat"})
    c.register("dig", lambda: {"dig"})
    c.register("composer", lambda: {"strike"})
    c.register("buffers", lambda: {"buf"})
    c.register("spares", lambda: {"spare"})
    return c


def _rules():
    return {n: SimpleNamespace(name=n) for n in list(RULE_HOOKS) + ["occupy_cell", "recruit"]}


def test_every_mover_gets_exactly_the_armies_of_higher_owners():
    rules = _rules()
    wire_claims(rules.values(), _claims())
    assert rules["army_composer"].excluded_source() == {"chat", "dig"}
    assert rules["buffer_leveling"].excluded_source() == {"chat", "dig", "strike"}
    assert rules["spare_armies"].excluded_source() == {"chat", "dig", "strike", "buf"}
    # the heal rule used to ignore buffers / spares: now it respects them
    assert {"buf", "spare"} <= rules["heal_routing"].locked_source()
    # logistics used to ignore the dig group and spares being sorted
    assert {"dig", "spare", "buf", "strike", "chat"} <= rules["logistics"].locked_source()
    assert {"chat", "dig", "strike", "buf", "spare"} <= rules["leveling"].excluded_source()


def test_occupy_and_recruit_keep_their_own_wiring():
    rules = _rules()
    wire_claims(rules.values(), _claims())
    assert not hasattr(rules["occupy_cell"], "locked_source")
    assert not hasattr(rules["recruit"], "locked_source")


def test_buffer_leveling_yields_cereal_to_the_composer():
    rules = _rules()
    comp = SimpleNamespace(cereal_need=620)
    wire_claims(rules.values(), _claims(), composer=comp)
    assert rules["buffer_leveling"].cereal_hold_source() == 620
    comp.cereal_need = 0
    assert rules["buffer_leveling"].cereal_hold_source() == 0
