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


def _hero(lv=1, uid="H"):
    return {"uid": uid, "id": 3201, "lv": lv, "portrayal": {"id": 320103, "level": 2}}


def test_a_weak_hero_swaps_out_like_any_weak_pawn_and_is_remembered():
    main = {"uid": "M", "pawns": [{"uid": "a", "id": 3201, "lv": 3}, _hero(1), {"uid": "c", "id": 3201, "lv": 2}]}
    buf = {"uid": "B", "pawns": [{"uid": "r1", "id": 3201, "lv": 3}, {"uid": "r2", "id": 3201, "lv": 3}]}
    assert bp.swap_pairs(main, buf, 3) == [("H", "r1"), ("c", "r2")]      # weakest first: the hero
    assert bp.home_of_swap(main, "H", "r1") == {"army": "M", "partner": "r1", "slot": 1}


def test_a_levelled_hero_only_goes_home_to_its_own_slot():
    homes = {"H": {"army": "M", "partner": "r1", "slot": 1}}
    main = {"uid": "M", "pawns": [{"uid": "a", "id": 3201, "lv": 3}, {"uid": "r1", "id": 3201, "lv": 3},
                                  {"uid": "c", "id": 3201, "lv": 2}]}
    buf = {"uid": "B", "pawns": [_hero(3), {"uid": "r2", "id": 3201, "lv": 3}]}
    # the hero returns into the slot r1 holds, FIRST; the other ready pawn serves the other weak one
    assert bp.swap_pairs(main, buf, 3, homes) == [("r1", "H"), ("c", "r2")]
    assert bp.pick_target([main], buf, 3, homes) == "M"
    # another army never receives the hero: the ready pool excludes it
    other = {"uid": "N", "pawns": [{"uid": "w", "id": 3201, "lv": 1}]}
    assert bp.swap_pairs(other, buf, 3, homes) == [("w", "r2")]
    # no ready partner and no weak pawn to give: nothing for a hero without a home army
    assert bp.swap_pairs(other, {"uid": "B", "pawns": [_hero(3)]}, 3, homes) == []


def test_home_falls_back_to_the_pawn_now_in_the_old_slot():
    homes = {"H": {"army": "M", "partner": "gone", "slot": 1}}
    main = {"uid": "M", "pawns": [{"uid": "a", "id": 3201, "lv": 3}, {"uid": "x", "id": 3201, "lv": 3}]}
    buf = {"uid": "B", "pawns": [_hero(3)]}
    assert bp.swap_pairs(main, buf, 3, homes) == [("x", "H")]


def test_the_buffer_never_trades_its_hero_away_in_reshape():
    target = {"uid": "T", "pawns": [{"uid": "t", "id": 3305, "lv": 1}]}
    buf = {"uid": "B", "pawns": [_hero(1), {"uid": "q", "id": 3201, "lv": 1}]}
    spare = {"uid": "S", "pawns": [{"uid": "s", "id": 3305, "lv": 3}]}
    trades = bp.reshape(buf, target, [spare], 3)
    assert all(out != "H" for out, _s, _i in trades)
