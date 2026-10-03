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


def test_recruit_stands_down_for_the_whole_time_the_composer_is_assembling():
    from nta_agent.runtime.claims_wiring import recruit_locked
    comp = SimpleNamespace(locked_uids=set(), assembling=True)
    assert recruit_locked(comp, {"chat"})            # non-empty: the generic top-up stops
    comp.assembling = False
    assert recruit_locked(comp, set()) == set()      # no goal: recruit works as before
    assert recruit_locked(comp, {"chat"}) == {"chat"}
    comp.locked_uids = {"A"}
    assert recruit_locked(comp, set()) == {"A"}
    assert recruit_locked(None, {"chat"}) == {"chat"}


def test_heal_may_still_route_the_dig_group_unless_the_player_holds_it():
    # live 2026-10-03: the dig waited 27 min on "heal" (dig_heal_wait) while the claims list had
    # taken the dig group away from HealRouting — the dig relies on it to heal its own group
    rules = _rules()
    claims = _claims()
    claims.register("dig", lambda: {"dig", "both"})
    claims.register("pawn_moves", lambda: {"chat", "both"})
    wire_claims(rules.values(), claims)
    blocked = rules["heal_routing"].locked_source()
    assert "dig" not in blocked                        # healing is part of the dig
    assert {"chat", "both", "strike", "buf", "spare"} <= blocked   # the rest still holds
    assert "dig" in rules["logistics"].locked_source()  # other rules stay off the dig group


def test_buffers_may_still_swap_with_an_army_only_the_dig_holds():
    rules = _rules()
    claims = _claims()
    claims.register("dig", lambda: {"d", "chat", "strike"})
    claims.register("pawn_moves", lambda: {"chat"})
    claims.register("composer", lambda: {"strike"})
    wire_claims(rules.values(), claims)
    assert rules["buffer_leveling"].dig_group_source() == {"d"}   # not the chat's, not the composer's
