from nta_agent.execution.armies import army_view


class FakeConfig:
    def __init__(self):
        self._t = {"pawnText": {"name_3101": {"vi": "Lính Trường Thương"}},
                   "equipText": {"name_6001": {"vi": "Kiếm Sắt"}}}

    def table(self, name):
        return self._t.get(name, {})


def test_army_view_orders_pawns_and_resolves_names():
    armys = [{
        "uid": "a1", "name": "Đội 1", "index": 109726, "state": 1, "marchSpeed": 120,
        "pawns": [
            {"uid": "p1", "id": 3101, "lv": 2, "attackSpeed": 6, "equip": {"id": 6001}},
            {"uid": "p2", "id": 3101, "lv": 1, "attackSpeed": 6, "equip": None},
        ],
    }]
    rows = army_view(armys, FakeConfig())
    assert len(rows) == 1
    r = rows[0]
    assert r["uid"] == "a1" and r["name"] == "Đội 1" and r["index"] == 109726
    assert r["state"] == 1 and r["state_label"] == "hành quân" and r["march_speed"] == 120
    assert r["pawns"] == [
        {"uid": "p1", "id": 3101, "name": "Lính Trường Thương", "lv": 2,
         "attack_speed": 6, "equip_name": "Kiếm Sắt"},
        {"uid": "p2", "id": 3101, "name": "Lính Trường Thương", "lv": 1,
         "attack_speed": 6, "equip_name": ""},
    ]


def test_unknown_state_and_names_fall_back():
    rows = army_view([{"uid": "a", "name": "", "index": 0, "state": 9, "marchSpeed": 0,
                       "pawns": [{"uid": "x", "id": 9999, "lv": 1, "attackSpeed": 5, "equip": {"id": 8888}}]}],
                     FakeConfig())
    assert rows[0]["state_label"] == "9"
    assert rows[0]["pawns"][0]["name"] == "#9999" and rows[0]["pawns"][0]["equip_name"] == "#8888"
