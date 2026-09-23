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


def test_max_count_reads_city_table_for_city_type():
    """A Cứ Điểm (city-type build) has bt_count 0 in buildBase but its real cap
    lives in the `city` table (bt_count 20). max_count must fall back to it."""
    c = GameConfig(_tables={
        "buildBase": {2102: {"id": 2102, "type": 2, "bt_count": 0, "ui": "BuildCity"},
                      2002: {"id": 2002, "type": 1, "bt_count": -3}},
        "city": {2102: {"id": 2102, "bt_count": 20}},
    })
    assert c.max_count(2102) == 20   # from city table, not buildBase's 0
    assert c.max_count(2002) == 3    # non-city build still uses buildBase
    assert c.max_count(999999) == 1  # unknown -> 1


def test_fort_max_count_is_20_live():
    c = GameConfig.load()
    assert c.max_count(2102) == 20   # Cứ Điểm cap (city.json bt_count)


def test_in_city_ids_filtered_by_room_type():
    c = GameConfig.load()
    # 2006 Chợ Tự Do server=0 (free); 2014 Chợ Liên Minh server="1,2" (newbie/ranked)
    newbie = c.in_city_build_ids(room_type=1)
    assert 2014 in newbie and 2006 not in newbie
    free = c.in_city_build_ids(room_type=0)
    assert 2006 in free and 2014 not in free
    both = c.in_city_build_ids()   # None -> no filter
    assert 2006 in both and 2014 in both
    # non-mode-gated building present in every mode
    assert 2004 in newbie and 2004 in free
