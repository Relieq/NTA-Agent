from nta_agent.execution.profile import Profile, composition_target


def _prof(comp):
    return Profile(army={"group": list(comp), "roles": {}, "onetile": True, "composition": comp},
                   occupy={})


def test_targets_biggest_unmet_gap():
    prof = _prof({"A": {3101: 3}, "B": {3305: 5}})
    armys = [{"uid": "A", "pawns": [{"id": 3101}]},        # has 1/3 -> gap 2
             {"uid": "B", "pawns": [{"id": 3305}, {"id": 3305}]}]  # 2/5 -> gap 3
    # both unlocked -> B's gap (3) wins
    assert composition_target(prof, armys, [3101, 3305]) == ("B", 3305)


def test_skips_locked_pawns():
    prof = _prof({"A": {3305: 3}})
    armys = [{"uid": "A", "pawns": []}]
    assert composition_target(prof, armys, [3101]) is None  # 3305 not unlocked


def test_none_when_targets_met():
    prof = _prof({"A": {3101: 2}})
    armys = [{"uid": "A", "pawns": [{"id": 3101}, {"id": 3101}]}]
    assert composition_target(prof, armys, [3101]) is None
