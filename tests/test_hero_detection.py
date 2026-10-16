"""A hero in an army shows up on the pawn as ``portrayal`` (live get_player_armys 2026-10-16:
Đội 1's 3201 pawn carries portrayal {id, attrs, level}); the old checks looked only for
``hero`` / ``avatarArmyUID`` and treated it as a plain soldier (dismissable, movable,
swapped out to a buffer as the 'weakest pawn')."""
from nta_agent.brain.guard import _is_hero as guard_is_hero
from nta_agent.execution import buffer_plan as bp
from nta_agent.execution.armies import army_view
from nta_agent.execution.army_composer import _is_hero

HERO = {"uid": "H", "id": 3201, "lv": 1, "portrayal": {"id": 320103, "level": 2}}


def test_portrayal_marks_a_pawn_as_hero_everywhere():
    assert _is_hero(HERO) and guard_is_hero(HERO)
    assert not _is_hero({"uid": "x", "id": 3201, "lv": 1})
    assert _is_hero({"uid": "x", "hero": True}) and _is_hero({"uid": "x", "avatarArmyUID": "a"})


def test_dashboard_view_keeps_the_hero_flag():
    class Cfg:
        def table(self, _n):
            return {}
    rows = army_view([{"uid": "A", "name": "Đội 1", "pawns": [HERO, {"uid": "p", "id": 3201, "lv": 1}]}], Cfg())
    assert [bool(p.get("hero")) for p in rows[0]["pawns"]] == [True, False]


def test_buffer_leveling_never_picks_the_hero_as_the_weak_pawn():
    main = {"uid": "M", "pawns": [{"uid": "a", "id": 3201, "lv": 3}, dict(HERO),
                                  {"uid": "c", "id": 3201, "lv": 2}]}
    buf = {"uid": "B", "pawns": [{"uid": "r1", "id": 3201, "lv": 3}, {"uid": "r2", "id": 3201, "lv": 3}]}
    assert bp.swap_pairs(main, buf, 3) == [("c", "r1")]          # the hero keeps its slot
    assert bp.demand([main], 3) == {3201: [{"uid": "c", "army_uid": "M", "lv": 2}]}
    assert bp.own_target([main], [3201], 3) is main              # still shaped for the real weak pawn
    only_hero = {"uid": "N", "pawns": [dict(HERO)]}
    assert bp.own_target([only_hero], [3201], 3) is None         # nothing to level but the hero
