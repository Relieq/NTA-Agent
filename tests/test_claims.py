import pytest

from nta_agent.execution.claims import ArmyClaims


def _claims():
    c = ArmyClaims()
    c.register("pawn_moves", lambda: {"chat"})
    c.register("dig", lambda: ["dig1", "dig2"])
    c.register("composer", lambda: {"strike"})
    c.register("buffers", lambda: {"buf", "away"})
    c.register("spares", lambda: {"spare"})
    return c


def test_an_owner_is_blocked_only_by_higher_priority_owners():
    c = _claims()
    assert c.blocked_for("pawn_moves") == set()
    assert c.blocked_for("dig") == {"chat"}
    assert c.blocked_for("composer") == {"chat", "dig1", "dig2"}
    assert c.blocked_for("buffers") == {"chat", "dig1", "dig2", "strike"}
    assert c.blocked_for("spares") == {"chat", "dig1", "dig2", "strike", "buf", "away"}


def test_a_rule_that_is_not_an_owner_ranks_below_everyone():
    c = _claims()
    assert c.blocked_for("leveling") == {"chat", "dig1", "dig2", "strike", "buf", "away", "spare"}


def test_owner_never_blocks_itself_and_unregistered_owner_holds_nothing():
    c = _claims()
    assert "buf" not in c.blocked_for("buffers")
    assert c.held_by("heal") == set()
    assert c.blocked_for("occupy") >= {"spare"}


def test_a_broken_provider_is_ignored():
    c = ArmyClaims()
    c.register("pawn_moves", lambda: 1 / 0)
    c.register("dig", lambda: {"d"})
    assert c.blocked_for("composer") == {"d"}


def test_unknown_owner_is_refused():
    with pytest.raises(ValueError):
        ArmyClaims().register("nobody", lambda: set())


def test_uids_are_compared_as_strings():
    c = ArmyClaims()
    c.register("dig", lambda: [123])
    assert c.blocked_for("composer") == {"123"}
