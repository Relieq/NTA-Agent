"""GameState store tests against a synthetic novice_data-shaped snapshot."""

from nta_agent.state import from_novice_data

# A trimmed snapshot mirroring the real slg_novice_data structure (no real account data).
NOVICE = {
    "cereal": 45, "timber": 102, "stone": 101, "iron": 0,
    "stamina": 97, "expBook": 0, "upScroll": 0, "fixator": 0,
    "noviceUser": {"gold": 30, "warToken": 0},
    "chapter": 1, "landScore": 6,
    "areas": {
        "870": {
            "index": 870, "owner": "911", "cityId": 1001, "landId": 10, "hp": [3, 3],
            "builds": [
                {"index": 870, "uid": "u1", "point": {"x": 2, "y": 5}, "id": 2001, "lv": 5},
                {"index": 870, "uid": "u2", "point": {"x": 0, "y": 1}, "id": 2004, "lv": 3},
            ],
        },
        "871": {
            "index": 871, "owner": "911", "cityId": -1001, "landId": 10, "hp": 0,
            "builds": [{"index": 871, "uid": "u3", "point": {"x": 0, "y": 0}, "id": 2101, "lv": 1}],
        },
    },
    "pawnSlots": {"1": {"lv": 1, "id": 3101}, "2": {"lv": 2, "id": 0}},
    "policySlots": {"3": {"lv": 3, "id": 0}},
    "equipSlots": {"1": {"lv": 1, "id": 0}},
    "heroSlots": [{"lv": 1, "avatarArmyUID": ""}],
    "marchs": [],
}

USER = {"uid": "57696053", "nickname": "Quyền Hoàng", "loginType": "google", "sessionId": "s1"}


def test_resources_parsed():
    st = from_novice_data(NOVICE)
    r = st.resources
    assert (r.cereal, r.timber, r.stone, r.iron) == (45, 102, 101, 0)
    assert r.gold == 30 and r.stamina == 97


def test_areas_and_buildings():
    st = from_novice_data(NOVICE)
    assert set(st.areas) == {870, 871}
    a = st.areas[870]
    assert a.city_id == 1001 and a.land_id == 10 and a.hp == (3, 3)
    assert len(a.buildings) == 2
    b = a.buildings[0]
    assert (b.id, b.lv, b.uid, b.point) == (2001, 5, "u1", (2, 5))
    # flat helper across all areas
    assert len(st.buildings()) == 3


def test_slots_and_heroes():
    st = from_novice_data(NOVICE)
    assert [(s.slot, s.lv, s.id) for s in st.pawn_slots] == [(1, 1, 3101), (2, 2, 0)]
    assert st.policy_slots[0].slot == 3
    assert len(st.heroes) == 1 and st.heroes[0].lv == 1


def test_main_city_picks_positive_cityid():
    st = from_novice_data(NOVICE)
    mc = st.main_city
    assert mc is not None and mc.index == 870  # 871 has a negative cityId


def test_user_applied_from_login():
    st = from_novice_data(NOVICE, user=USER)
    assert st.user.uid == "57696053"
    assert st.user.nickname == "Quyền Hoàng"
    assert st.user.login_type == "google"


def test_raw_escape_hatch_preserves_everything():
    st = from_novice_data(NOVICE)
    # unmodelled fields still reachable via raw
    assert st.raw["noviceUser"]["warToken"] == 0
    assert st.source == "novice"


def test_from_entry_rst_live_shape():
    from nta_agent.state import from_entry_rst
    rst = {
        "sid": 1001989, "mapSize": {"x": 600, "y": 600},
        "player": {
            "uid": "57696053",
            "cereal": {"value": 701, "opHour": 116},
            "timber": {"value": 702, "opHour": 120},
            "stone": {"value": 700, "opHour": 120},
            "stamina": 97, "landCount": 3,
            "heroSlots": [{"lv": 1}, {"lv": 10}, {"lv": 15}],
        },
        "world": {"mapId": 5, "season": 2},
    }
    st = from_entry_rst(rst)
    assert st.source == "api"
    assert st.user.uid == "57696053"
    assert (st.resources.cereal, st.resources.timber, st.resources.stone) == (701, 702, 700)
    assert st.resources.stamina == 97
    assert [h.lv for h in st.heroes] == [1, 10, 15]
    assert st.raw["mapSize"] == {"x": 600, "y": 600}


def test_apply_notify_updates_resources():
    from nta_agent.state import apply_notify, from_entry_rst
    st = from_entry_rst({"player": {"uid": "1", "cereal": {"value": 100}, "iron": 0}})
    # a resource notify (type 1 -> data_1 = UpdateOutPut)
    notify = {"list": [
        {"type": 1, "data_1": {
            "cereal": {"value": 250, "opHour": 116},
            "timber": {"value": 300},
            "iron": 5, "gold": 42,
        }},
    ]}
    apply_notify(st, notify)
    assert st.resources.cereal == 250
    assert st.resources.timber == 300
    assert st.resources.iron == 5
    assert st.resources.gold == 42


def test_apply_notify_updates_build_queue():
    from nta_agent.state import apply_notify, from_entry_rst
    st = from_entry_rst({"player": {"uid": "1",
        "btQueues": [{"index": 5, "uid": "b1", "id": 2001, "lv": 6,
                      "needTime": 820000, "surplusTime": 543894}]}})
    assert len(st.build_queue) == 1
    # UPDATE_BT_QUEUE (type 6, data_6 = repeated BTInfo). A finished build sends the
    # queue WITHOUT it — here empty -> the stale queue must clear.
    apply_notify(st, {"list": [{"type": 6, "data_6": []}]})
    assert st.build_queue == []
    # a fresh queue replaces the list
    apply_notify(st, {"list": [{"type": 6, "data_6": [
        {"index": 5, "uid": "b2", "id": 2002, "lv": 3, "surplusTime": 1000}]}]})
    assert [b["id"] for b in st.build_queue] == [2002]


def test_apply_notify_updates_building_level():
    from nta_agent.state import apply_notify, from_entry_rst
    st = from_entry_rst({"player": {"uid": "1", "mainCityIndex": 5,
        "builds": [{"index": 5, "uid": "b1", "id": 2001, "lv": 5}]}})
    assert [(b.id, b.lv) for b in st.builds] == [(2001, 5)]
    # AreaBuildInfo (type 5, data_5): the completed build at its new level.
    apply_notify(st, {"list": [{"type": 5, "data_5": {
        "index": 5, "uid": "b1", "id": 2001, "lv": 6, "point": {"x": 1, "y": 2}}}]})
    b = next(b for b in st.builds if b.uid == "b1")
    assert b.lv == 6
