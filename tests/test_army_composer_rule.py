"""ArmyComposer rule: drives the composition planner against live-ish Actions."""

from types import SimpleNamespace

from nta_agent.execution.heuristics import ArmyComposer
from nta_agent.execution.profile import load_profile

CITY = 100
TARGET = [{"pawn_id": 3206, "armies": 1, "size": 3},
          {"pawn_id": 3305, "armies": 2, "size": 3}]


def _profile(target):
    p = load_profile("nonexistent")   # defaults
    p.army["strike_target"] = target
    return p


def _army(uid, ids, index=CITY):
    return {"uid": uid, "index": index, "state": 0,
            "pawns": [{"uid": f"{uid}p{i}", "id": x, "lv": 1} for i, x in enumerate(ids)]}


def _state(unlocked=(3206, 3305)):
    slots = {str(i): {"id": pid} for i, pid in enumerate(unlocked, 1)}
    return SimpleNamespace(main_city_index=CITY, raw={"player": {"pawnSlots": slots}})


class FakeActions:
    def __init__(self, armies):
        self._armies = armies
        self.calls = []

    def get_player_armys(self):
        return self._armies

    def building_uid(self, bid):
        return "barracks1"

    def move_cell_army(self, armies, to):
        self.calls.append(("rally", sorted(a["uid"] for a in armies), to))

    def change_pawn_army(self, index, army_uid, pawn_uid, new_army_uid, **kw):
        self.calls.append(("move", army_uid, pawn_uid, new_army_uid))

    def dismiss_pawn(self, index, army_uid, pawn_uid):
        self.calls.append(("dismiss", army_uid, pawn_uid))

    def drill_pawn(self, bu, pid, army_uid="", army_name="", **kw):
        self.calls.append(("recruit", pid, army_uid or army_name))


def test_no_target_stands_down_and_unlocks():
    r = ArmyComposer(profile=_profile([]))
    r.locked_uids = {"x"}
    assert r.applies(_state(), FakeActions([_army("a", [3206] * 3)])) is False
    assert r.locked_uids == set()


def test_rallies_scattered_and_locks_only_incomplete():
    # imp1 is short (incomplete) -> locked; tank & imp2 are complete -> RELEASED so
    # occupy can farm them. A scattered donor holding 3305 is rallied to the city.
    armies = [_army("tank", [3206, 3206, 3206]), _army("imp1", [3305]),
              _army("imp2", [3305, 3305, 3305]), _army("donor", [3305, 3305, 3305], index=250)]
    r = ArmyComposer(profile=_profile(TARGET))
    r._strike_uids = ["tank", "imp1", "imp2"]
    acts = FakeActions(armies)
    assert r.applies(_state(), acts) is True
    r.act(acts)
    assert any(c[0] == "rally" and "donor" in c[1] for c in acts.calls)
    assert r.locked_uids == {"imp1"}                   # only the incomplete army is locked
    assert "tank" not in r.locked_uids and "imp2" not in r.locked_uids   # completed -> released


def test_completed_armies_all_released():
    # every strike army complete -> none locked (all free to farm; group regroups later).
    armies = [_army("tank", [3206, 3206, 3206]), _army("imp1", [3305, 3305, 3305]),
              _army("imp2", [3305, 3305, 3305])]
    r = ArmyComposer(profile=_profile(TARGET))
    r._strike_uids = ["tank", "imp1", "imp2"]
    r.applies(_state(), FakeActions(armies))
    assert r.locked_uids == set()


def test_moves_pawns_from_donor_when_colocated():
    armies = [_army("tank", [3206, 3206, 3206]), _army("imp1", [3305]),
              _army("imp2", [3305, 3305, 3305]), _army("donor", [3305, 3305, 3101])]
    r = ArmyComposer(profile=_profile(TARGET))
    r._strike_uids = ["tank", "imp1", "imp2"]
    acts = FakeActions(armies)
    assert r.applies(_state(), acts) is True
    r.act(acts)
    moves = [c for c in acts.calls if c[0] == "move"]
    assert moves and all(c[1] == "donor" and c[3] == "imp1" for c in moves)


def test_dismisses_low_level_leftover_pawn():
    # imp1 clogged with a lv1 3101 and no donor room -> dismiss_pawn dispatched.
    armies = [_army("tank", [3206, 3206, 3206]),
              {"uid": "imp1", "index": CITY, "state": 0,
               "pawns": [{"uid": "k0", "id": 3305, "lv": 1}, {"uid": "k1", "id": 3101, "lv": 1}]},
              _army("imp2", [3305, 3305, 3305])]
    r = ArmyComposer(profile=_profile(TARGET))
    r._strike_uids = ["tank", "imp1", "imp2"]
    acts = FakeActions(armies)
    assert r.applies(_state(), acts) is True
    r.act(acts)
    assert ("dismiss", "imp1", "k1") in acts.calls


def test_act_continues_past_benign_action_failure():
    # a benign per-action failure (e.g. 500017) must NOT abort the batch — the recruit
    # at the end still runs (the live-run bug: act() returned on the first failure).
    class Acts(FakeActions):
        def change_pawn_army(self, index, army_uid, pawn_uid, new_army_uid, **kw):
            raise RuntimeError("game/HD_ChangePawnArmy: ecode.500017")
    acts = Acts([_army("imp1", [3305])])
    r = ArmyComposer(profile=_profile(TARGET))
    r._city = CITY
    r._plan = {"actions": [
        {"op": "move_pawn", "from": "d", "pawn": "p", "to": "imp1"},   # fails benign
        {"op": "recruit", "pawn_id": 3305, "army": "imp1", "count": 5}]}
    r.act(acts)
    assert any(c[0] == "recruit" for c in acts.calls)   # recruit still executed


def test_recruit_into_new_army_passes_valid_name():
    """When no strike army of the type has room, the plan's recruit targets a NEW army
    (army=None). drill_pawn must then get a non-empty army_name — an empty name is
    rejected by the server with ecode.500070 "special characters" (live soak bug:
    the composer could never create strike armies and deadlocked)."""
    seen = []

    class Acts(FakeActions):
        def drill_pawn(self, bu, pid, army_uid="", army_name="", **kw):
            seen.append((army_uid, army_name))

    acts = Acts([{**_army("a1", [3101]), "name": "D1"}])   # an existing army named "D1"
    r = ArmyComposer(profile=_profile(TARGET))
    r._city = CITY
    r._plan = {"actions": [{"op": "recruit", "pawn_id": 3305, "army": None, "count": 9}]}
    r.act(acts)
    assert seen, "recruit must still be attempted"
    uid, name = seen[0]
    assert uid == "" and name                  # new army, WITH a name
    assert name != "D1"                        # not colliding with an existing army


def test_act_treats_queue_full_500018_as_benign():
    class Acts(FakeActions):
        def drill_pawn(self, bu, pid, army_uid="", army_name="", **kw):
            raise RuntimeError("game/HD_DrillPawn: ecode.500018")   # recruit queue full
    events = []
    acts = Acts([_army("imp1", [3305])])
    r = ArmyComposer(profile=_profile(TARGET), on_event=lambda k, d: events.append((k, d)))
    r._city = CITY
    r._plan = {"actions": [{"op": "recruit", "pawn_id": 3305, "army": "imp1", "count": 5}]}
    r.act(acts)
    assert not any(k == "composition_error" for k, _ in events)   # benign, not surfaced


def test_recruits_deficit():
    armies = [_army("tank", [3206, 3206, 3206]), _army("imp1", [3305]), _army("imp2", [])]
    r = ArmyComposer(profile=_profile(TARGET))
    r._strike_uids = ["tank", "imp1", "imp2"]
    acts = FakeActions(armies)
    assert r.applies(_state(), acts) is True
    r.act(acts)
    assert any(c[0] == "recruit" and c[1] == 3305 for c in acts.calls)


def test_blocked_emits_event_and_backs_off():
    armies = [_army("imp1", [3305])]
    events = []
    status = []
    r = ArmyComposer(profile=_profile(TARGET), on_event=lambda k, d: events.append((k, d)),
                     status_sink=status.append)
    # 3305 locked (not in unlocked) and short -> infeasible
    assert r.applies(_state(unlocked=(3206,)), FakeActions(armies)) is False
    assert any(k == "composition_blocked" for k, _ in events)
    assert r._cooldown > 0
    # status persisted for the brain advice loop: blocked + issues
    assert status and status[-1]["blocked"] is True and status[-1]["issues"]


def test_status_active_false_when_no_target():
    status = []
    r = ArmyComposer(profile=_profile([]), status_sink=status.append)
    r.applies(_state(), FakeActions([_army("a", [3206] * 3)]))
    assert status[-1] == {"active": False}


def test_done_when_target_met():
    armies = [_army("tank", [3206, 3206, 3206]), _army("imp1", [3305, 3305, 3305]),
              _army("imp2", [3305, 3305, 3305])]
    r = ArmyComposer(profile=_profile(TARGET))
    r._strike_uids = ["tank", "imp1", "imp2"]
    assert r.applies(_state(), FakeActions(armies)) is False   # nothing to do


def test_reserved_farm_group_not_pulled():
    p = _profile(TARGET)
    p.army["group"] = ["farm"]       # farm is the active group -> reserved
    armies = [_army("farm", [3305, 3305, 3305]), _army("tank", [3206, 3206, 3206]),
              _army("imp1", [3305]), _army("imp2", [3305, 3305, 3305])]
    r = ArmyComposer(profile=p)
    r._strike_uids = ["tank", "imp1", "imp2"]
    acts = FakeActions(armies)
    r.applies(_state(), acts)
    r.act(acts)
    assert all(c[1] != "farm" for c in acts.calls if c[0] == "move")


def test_done_clears_target_one_shot():
    """strike_target is a ONE-SHOT goal: once the group is assembled the composer
    clears it (in memory + via target_sink, which persists it to disk) and stands
    down — it must not keep re-activating and fighting occupy for the armies."""
    armies = [_army("tank", [3206, 3206, 3206]), _army("imp1", [3305, 3305, 3305]),
              _army("imp2", [3305, 3305, 3305])]
    prof = _profile(TARGET)
    sunk, events = [], []
    r = ArmyComposer(profile=prof, target_sink=lambda: sunk.append(1),
                     on_event=lambda k, d: events.append(k))
    r._strike_uids = ["tank", "imp1", "imp2"]
    assert r.applies(_state(), FakeActions(armies)) is False
    assert sunk == [1]
    assert prof.army["strike_target"] == []
    assert "composition_done" in events
    # next tick: no goal -> stands down, releases every lock, sink not called again
    assert r.applies(_state(), FakeActions(armies)) is False
    assert sunk == [1] and r.locked_uids == set()


class NamingActions(FakeActions):
    def rename_army(self, index, army_uid, name):
        self.calls.append(("rename", army_uid, name, index))


def test_done_names_the_group_in_target_order():
    """The names the player gave ('Đội 1'..'Đội 5') are applied once assembled."""
    target = [{"pawn_id": 3206, "armies": 1, "size": 3, "names": ["Đội 1"]},
              {"pawn_id": 3305, "armies": 2, "size": 3, "names": ["Đội 2", "Đội 3"]}]
    armies = [_army("tank", [3206] * 3), _army("imp1", [3305] * 3), _army("imp2", [3305] * 3)]
    r = ArmyComposer(profile=_profile(target))
    r._strike_uids = ["tank", "imp1", "imp2"]
    acts = NamingActions(armies)
    assert r.applies(_state(), acts) is False
    assert [c[1:3] for c in acts.calls if c[0] == "rename"] == \
        [("tank", "Đội 1"), ("imp1", "Đội 2"), ("imp2", "Đội 3")]


def test_done_skips_armies_already_named_and_entries_without_names():
    target = [{"pawn_id": 3206, "armies": 1, "size": 3},
              {"pawn_id": 3305, "armies": 2, "size": 3, "names": ["Đội 2"]}]
    armies = [_army("tank", [3206] * 3), _army("imp1", [3305] * 3), _army("imp2", [3305] * 3)]
    armies[1]["name"] = "Đội 2"
    r = ArmyComposer(profile=_profile(target))
    r._strike_uids = ["tank", "imp1", "imp2"]
    acts = NamingActions(armies)
    r.applies(_state(), acts)
    assert [c for c in acts.calls if c[0] == "rename"] == []


def test_cleared_goal_releases_armies_even_during_blocked_cooldown():
    """2026-09-25: clearing a blocked goal left 5 armies locked ~5 min (cooldown)."""
    r = ArmyComposer(profile=_profile(TARGET))
    r.locked_uids = {"a", "b"}
    r._cooldown = 60
    r.profile.army["strike_target"] = []
    assert r.applies(_state(), FakeActions([])) is False
    assert r.locked_uids == set() and r._cooldown == 0


def test_complete_armies_are_named_while_the_group_is_still_assembling():
    """2026-09-25: 4 IMP armies were full but kept 'D2'/'D1' until the whole group
    (waiting on 7 recruits) was done. Name each army as soon as it's complete."""
    target = [{"pawn_id": 3206, "armies": 1, "size": 3, "names": ["Đội 1"]},
              {"pawn_id": 3305, "armies": 2, "size": 3, "names": ["Đội 2", "Đội 3"]}]
    armies = [_army("tank", [3206]), _army("imp1", [3305] * 3), _army("imp2", [3305] * 3)]
    r = ArmyComposer(profile=_profile(target))
    r._strike_uids = ["tank", "imp1", "imp2"]
    acts = NamingActions(armies)
    r.applies(_state(), acts)
    renamed = [c[1:3] for c in acts.calls if c[0] == "rename"]
    assert ("imp1", "Đội 2") in renamed and ("imp2", "Đội 3") in renamed
    assert all(u != "tank" for u, _ in renamed)          # incomplete: not yet


def test_failed_rename_backs_off_instead_of_retrying_every_tick():
    class Busy(NamingActions):
        def rename_army(self, index, army_uid, name):
            self.calls.append(("rename", army_uid, name, index))
            raise RuntimeError("ecode.500036")
    target = [{"pawn_id": 3305, "armies": 1, "size": 3, "names": ["Đội 2"]},
              {"pawn_id": 3206, "armies": 1, "size": 3}]
    armies = [_army("imp1", [3305] * 3), _army("tank", [3206])]
    r = ArmyComposer(profile=_profile(target), rename_retry_ticks=3)
    r._strike_uids = ["imp1", "tank"]
    acts = Busy(armies)
    for _ in range(3):
        r._cooldown = 0
        r.applies(_state(), acts)
    assert sum(1 for c in acts.calls if c[0] == "rename") == 1


def test_group_names_are_stable_when_the_assignment_order_changes():
    """2026-09-25 11:53: the planner's order changed and 'Đội 4' became 'Đội 5' while
    'Đội 2'/'Đội 3' were re-assigned (ecode 500061). A name the group already gave an
    army sticks; only armies without a group name get the free ones."""
    target = [{"pawn_id": 3305, "armies": 3, "size": 3, "names": ["Đội 2", "Đội 3", "Đội 4"]}]
    armies = [_army("new", [3305] * 3), _army("a", [3305] * 3), _army("b", [3305] * 3)]
    armies[1]["name"], armies[2]["name"] = "Đội 2", "Đội 4"
    r = ArmyComposer(profile=_profile(target))
    acts = NamingActions(armies)
    r._name_group(acts, target, [{"uid": "new", "pawn_id": 3305}, {"uid": "a", "pawn_id": 3305},
                                 {"uid": "b", "pawn_id": 3305}], {x["uid"]: x for x in armies})
    assert [c[1:3] for c in acts.calls if c[0] == "rename"] == [("new", "Đội 3")]


def test_rally_skips_armies_in_battle_and_the_batch_continues():
    """500036 (in battle) on a rally aborted the whole batch ~every minute (26x)."""
    target = [{"pawn_id": 3305, "armies": 1, "size": 3}]
    far = _army("far", [3305], index=999)
    far["state"] = 2                                   # fighting
    r = ArmyComposer(profile=_profile(target))
    r._city = CITY
    r._plan = {"actions": [{"op": "rally", "uids": ["far"], "to": CITY},
                           {"op": "move_pawn", "from": "d", "pawn": "p", "to": "far"}]}
    acts = NamingActions([far])
    r.act(acts)
    assert not any(c[0] == "rally" for c in acts.calls)
    assert any(c[0] == "move" for c in acts.calls)
