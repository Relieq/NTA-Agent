from nta_agent.execution.fort_advisor import can_build_fort, fort_zone

W = 600
def idx(x, y): return y * W + x


def test_fort_zone_is_owned_cells_beyond_radius():
    main = idx(100, 100)
    owned = {idx(103, 100), idx(108, 100), idx(100, 110), main}  # 103 in-zone(<=6), others out
    z = fort_zone(main, owned, forts=[], radius=6)
    assert idx(108, 100) in z and idx(100, 110) in z
    assert idx(103, 100) not in z          # within free radius
    assert main not in z                    # not the city itself


def test_fort_zone_excludes_forts_and_near_enemy():
    main = idx(100, 100)
    owned = {idx(108, 100), idx(100, 112)}
    z = fort_zone(main, owned, forts=[idx(108, 100)], radius=6)
    assert idx(108, 100) not in z          # already a fort
    z2 = fort_zone(main, owned, forts=[], radius=6, enemy=[idx(100, 114)], danger_radius=4)
    assert idx(100, 112) not in z2         # too close to enemy


def test_can_build_fort_validates_zone_and_cap():
    main = idx(100, 100)
    owned = {idx(108, 100), idx(103, 100)}
    ok, _ = can_build_fort(idx(108, 100), main, owned, forts=[], cap=3, radius=6)
    assert ok
    ok2, _ = can_build_fort(idx(103, 100), main, owned, forts=[], cap=3, radius=6)
    assert not ok2                          # in free radius -> not allowed
    ok3, _ = can_build_fort(idx(108, 100), main, owned, forts=[1, 2, 3], cap=3)
    assert not ok3                          # cap reached
