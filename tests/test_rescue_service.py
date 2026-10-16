"""RescueService: tracks origins, and hands 'rescued pawn -> its army' to the pawn-move queue."""
from types import SimpleNamespace

from nta_agent.execution.injury import NEW_ARMY_NAME
from nta_agent.runtime.pawn_move_queue import PawnMoveQueue
from nta_agent.runtime.rescue_service import RescueService

W = 600
CITY = 100 * W + 100
FIELD = 110 * W + 100


def A(uid, name, index=CITY, n=9, pid=3305):
    return {"uid": uid, "name": name, "index": index, "state": 0,
            "pawns": [{"uid": f"{uid}-{k}", "id": pid, "lv": 2} for k in range(n)]}


class Acts:
    def __init__(self, armies):
        self.armies = armies

    def get_player_armys(self):
        return self.armies


def _state(injured=()):
    return SimpleNamespace(main_city_index=CITY,
                           raw={"player": {"injuryPawns": [{"uid": u} for u in injured]}})


def _svc(tmp_path, armies, **kw):
    from nta_agent.execution.rescue import OriginBook
    q = PawnMoveQueue(tmp_path / "q.json")
    events = []
    s = RescueService(Acts(armies), q, OriginBook(tmp_path / "o.json"),
                      profile=SimpleNamespace(army={"group": ["H"], "presets": {}, "active": ""}),
                      territory_source=lambda: ({FIELD, CITY, FIELD + 1}, []),
                      on_event=lambda k, d: events.append((k, d)), every=1, **kw)
    return s, q, events


def _rescued(armies):
    r = A("R", NEW_ARMY_NAME, n=0)
    r["pawns"] = [{"uid": "H-0", "id": 3305, "lv": 2}]
    return armies + [r]


def test_a_rescued_pawn_is_sent_home_with_a_gather_job(tmp_path):
    home = A("H", "Đội 2", index=FIELD, n=8)
    s, q, ev = _svc(tmp_path, [home])
    s.tick(_state())                                    # the pawn is alive in H: origin recorded
    home["pawns"].pop(0)                                # it dies ...
    s.tick(_state(injured=["H-0"]))
    s.actions.armies = _rescued([home])                 # ... and is revived into the rescue army
    s.tick(_state())
    job = next(iter(q.pending().values()))
    assert (job["op"], job["from"], job["to"], job["pawn_uids"]) == ("move", "R", "H", ["H-0"])
    assert job["gather"] is True and job["meet"] == FIELD     # the rescue walks to the home army
    assert {"R", "H"} <= q.army_uids()
    assert s.rescue_uids() == {"R"}
    assert any(k == "rescue_return" for k, _ in ev)


def test_no_second_job_while_the_first_is_pending(tmp_path):
    home = A("H", "Đội 2", index=FIELD, n=8)
    s, q, _ = _svc(tmp_path, [home])
    s.tick(_state())
    s.actions.armies = _rescued([home])
    s.tick(_state())
    s.tick(_state())
    assert len(q.pending()) == 1


def test_same_cell_means_no_gather(tmp_path):
    home = A("H", "Đội 2", index=CITY, n=8)
    s, q, _ = _svc(tmp_path, [home])
    s.tick(_state())
    s.actions.armies = _rescued([home])
    s.tick(_state())
    job = next(iter(q.pending().values()))
    assert job["gather"] is False and job["meet"] is None


def test_the_slot_stays_reserved_while_the_pawn_is_dead_or_waiting(tmp_path):
    home = A("H", "Đội 2", index=FIELD, n=8)
    s, _q, _ = _svc(tmp_path, [home])
    s.tick(_state())
    home["pawns"].pop(0)
    s.tick(_state(injured=["H-0"]))
    assert s.vacancy_uids() == {"H"}                    # dead in the infirmary: no recruit takes the slot
    s.actions.armies = _rescued([home])
    s.tick(_state())
    assert "H" in s.vacancy_uids()


def test_a_home_army_off_our_land_meets_the_rescue_at_the_main_city(tmp_path):
    home = A("H", "Đội 2", index=FIELD + 50, n=8)       # standing where no owned cell is near
    s, q, _ = _svc(tmp_path, [home])
    s.territory_source = lambda: (set(), [])
    s.tick(_state())
    s.actions.armies = _rescued([home])
    s.tick(_state())
    job = next(iter(q.pending().values()))
    assert job["gather"] is True and job["meet"] == CITY
