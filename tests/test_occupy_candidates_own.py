"""Cell defenders must exclude MY armies standing/fighting there (live 2026-09-25:
26 of 27 'enemy' pawns in a forecast were our own -> the sim fought copies of our
armies forever: 13 'sidecar timed out' + 6 'reading map' on their treasures)."""
from nta_agent.execution.occupy_planner import discover_around, discover_frontier

ME = "me"
W = 600


def _area(owner_armies):
    return {"owner": "", "landId": 7, "hp": [6, 6],
            "armys": [{"owner": o, "pawns": [{"uid": f"{o}{i}", "id": pid} for i in range(n)]}
                      for o, pid, n in owner_armies]}


def test_frontier_defenders_exclude_my_armies():
    areas = {5: _area([(ME, 3305, 9), ("", 4111, 2)]),     # mine + NPC guardians
             6: _area([(ME, 3305, 9)])}                     # only my army there
    out = {c.index: c for c in discover_frontier(lambda i: areas.get(i, {}), [5, 6], ME)}
    assert [p["id"] for p in out[5].defenders] == [4111, 4111]
    assert 6 not in out                                      # nothing hostile to fight


def test_discover_around_defenders_exclude_my_armies():
    city = 10 * W + 10
    areas = {city: {"owner": ME}, city + 1: _area([(ME, 3305, 9), ("enemy", 3201, 3)])}
    out = discover_around(lambda i: areas.get(i, {}), [city], 1, ME)
    c = next(c for c in out if c.index == city + 1)
    assert {p["id"] for p in c.defenders} == {3201}
