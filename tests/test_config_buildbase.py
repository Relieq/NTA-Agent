from nta_agent.data.config import GameConfig


def test_max_count_and_in_city_ids():
    c = GameConfig.load()
    assert c.max_count(2002) == 3    # Kho Lương bt_count -3
    assert c.max_count(2001) == 1    # Thành Chính bt_count -1
    assert c.max_count(999999) == 1  # unknown -> 1
    ids = c.in_city_build_ids()
    assert 2001 in ids and 2004 in ids   # main hall, barracks
    assert 3001 not in ids               # ancient capital (type 2) excluded
    assert c.build_base(2001)["ui"] == "BuildMainInfo"
