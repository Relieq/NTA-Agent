"""Revived pawns go back to the army they died in: origin book, return planning, the revive
target (never a spare / buffer), and the fillers (recruit) that must not take the slot."""
from nta_agent.execution import rescue as rs
from nta_agent.execution.injury import NEW_ARMY_NAME, revive_target

CITY = 100


def A(uid, name, index=CITY, n=9, pid=3305, state=0, drill=0):
    return {"uid": uid, "name": name, "index": index, "state": state,
            "pawns": [{"uid": f"{uid}-{k}", "id": pid, "lv": 2} for k in range(n)],
            "drillPawns": [pid] * drill}


# ---- origin book ---------------------------------------------------------------------
def test_book_remembers_the_army_a_pawn_stood_in_and_keeps_it_through_the_rescue(tmp_path):
    book = rs.OriginBook(tmp_path / "o.json")
    a = A("M", "Đội 2", n=3)
    book.update([a], injured=[])
    assert book.origin("M-0") == "M"
    # the pawn dies: gone from every army, listed as injured -> the origin stays
    a["pawns"].pop(0)
    book.update([a], injured=[{"uid": "M-0"}])
    assert book.origin("M-0") == "M"
    # revived into the rescue army: the origin must NOT become "Cứu Hộ"
    rescue = A("R", NEW_ARMY_NAME, n=0)
    rescue["pawns"] = [{"uid": "M-0", "id": 3305, "lv": 2}]
    book.update([a, rescue], injured=[])
    assert book.origin("M-0") == "M"
    # back in a normal army -> that army is its new origin; persisted across a restart
    a["pawns"].append(rescue["pawns"].pop())
    book.update([a, rescue], injured=[])
    assert rs.OriginBook(tmp_path / "o.json").origin("M-0") == "M"


def test_book_forgets_pawns_that_are_gone(tmp_path):
    book = rs.OriginBook(tmp_path / "o.json", keep_s=10)
    a = A("M", "Đội 2", n=2)
    book.update([a], injured=[], now=0)
    a["pawns"].pop()
    book.update([a], injured=[], now=100)           # neither alive nor injured for > keep_s
    assert book.origin("M-1") is None and book.origin("M-0") == "M"


# ---- planning ------------------------------------------------------------------------
def test_each_rescued_pawn_goes_home_when_the_home_army_has_room(tmp_path):
    book = rs.OriginBook(tmp_path / "o.json")
    home1, home2 = A("H1", "Đội 1", n=8, pid=3201), A("H2", "Đội 2", n=8)
    rescue = {"uid": "R", "name": NEW_ARMY_NAME, "index": CITY, "state": 0, "pawns": [
        {"uid": "p1", "id": 3201, "lv": 2}, {"uid": "p2", "id": 3305, "lv": 2}]}
    book.set("p1", "H1")
    book.set("p2", "H2")
    plans = rs.plan_returns([home1, home2, rescue], book, group=["H2", "H1"])
    assert {(p["from"], p["to"], tuple(p["pawns"])) for p in plans} == {
        ("R", "H1", ("p1",)), ("R", "H2", ("p2",))}


def test_unknown_origin_falls_back_to_the_group_army_missing_that_type(tmp_path):
    book = rs.OriginBook(tmp_path / "o.json")
    g = [A("G1", "Đội 1", n=9), A("G2", "Đội 2", n=8), A("G3", "Đội 3", n=8)]
    rescue = {"uid": "R", "name": NEW_ARMY_NAME, "index": CITY, "state": 0,
              "pawns": [{"uid": "x", "id": 3305, "lv": 2}]}
    plans = rs.plan_returns(g + [rescue], book, group=["G1", "G2", "G3"])
    assert [(p["to"], p["pawns"]) for p in plans] == [("G2", ["x"])]     # first with room, group order


def test_a_full_home_army_or_one_with_recruits_in_training_is_not_a_target(tmp_path):
    book = rs.OriginBook(tmp_path / "o.json")
    full = A("F", "Đội 1", n=9)
    training = A("T", "Đội 2", n=8, drill=1)       # the last slot is already being drilled
    rescue = {"uid": "R", "name": NEW_ARMY_NAME, "index": CITY, "state": 0,
              "pawns": [{"uid": "a", "id": 3305, "lv": 2}, {"uid": "b", "id": 3305, "lv": 2}]}
    book.set("a", "F")
    book.set("b", "T")
    assert rs.plan_returns([full, training, rescue], book, group=["F", "T"]) == []


def test_two_pawns_never_overfill_one_target(tmp_path):
    book = rs.OriginBook(tmp_path / "o.json")
    home = A("H", "Đội 1", n=8)
    rescue = {"uid": "R", "name": NEW_ARMY_NAME, "index": CITY, "state": 0,
              "pawns": [{"uid": "a", "id": 3305, "lv": 2}, {"uid": "b", "id": 3305, "lv": 2}]}
    book.set("a", "H")
    book.set("b", "H")
    plans = rs.plan_returns([home, rescue], book, group=["H"])
    assert [(p["to"], p["pawns"]) for p in plans] == [("H", ["a"])]      # 8 + 1 = 9


# ---- revive target -------------------------------------------------------------------
def test_revive_goes_to_the_origin_army_when_it_is_at_the_city_with_room():
    origin = A("O", "Đội 1", n=8)
    spare = A("S", "D1", n=5)
    assert revive_target([spare, origin], CITY, 9, origin="O") == ("O", "Đội 1")


def test_revive_never_uses_a_spare_or_buffer_even_with_room():
    spare, buf = A("S", "D1", n=5), A("B", "Nâng Cấp 1", n=3)
    assert revive_target([spare, buf], CITY, 9, origin="gone") == ("", NEW_ARMY_NAME)


def test_revive_reuses_the_rescue_army_and_names_a_second_one_when_it_is_full():
    rescue = A("R", NEW_ARMY_NAME, n=1)
    assert revive_target([rescue], CITY, 9) == ("R", NEW_ARMY_NAME)
    full = A("R", NEW_ARMY_NAME, n=9)
    assert revive_target([full], CITY, 9) == ("", NEW_ARMY_NAME + " 2")
    away = A("R", NEW_ARMY_NAME, n=1, index=CITY + 5)           # delivering: not at the city
    assert revive_target([away], CITY, 9) == ("", NEW_ARMY_NAME + " 2")
