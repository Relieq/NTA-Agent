"""'Thay 1 IMP cuối Đội 5 thành 1 Thợ Săn' when NO army holds a Thợ Săn (player 2026-10-03:
'tự chiêu mộ thêm 1 lính thợ săn rồi tráo với lính imp ấy'): the confirmed job recruits the
pawn first (into a roomy idle IMP army at the city, else a new army), waits for the training,
then swaps it with the chosen IMP."""
from nta_agent.dashboard.server import pawn_move_label
from nta_agent.execution.pawn_moves import sanitize_pawn_moves
from nta_agent.runtime.pawn_move_queue import PawnMoveQueue

CITY = 500


def _army(uid, name, types, index=CITY, state=0, drilling=()):
    return {"uid": uid, "name": name, "index": index, "state": state,
            "drillPawns": list(drilling),
            "pawns": [{"uid": f"{uid}{i}", "id": t, "lv": 1 + i} for i, t in enumerate(types)]}


def _armies():
    return [_army("F", "Đội 5", [3305] * 9, state=1),            # marching, full of IMP
            _army("S", "Đội 6", [3305] * 3),                      # idle IMP army with room
            _army("N", "Nâng Cấp 1", [3305] * 4)]                  # a buffer: never the host


SPEC = {"op": "swap", "army_a": "F", "pawn_a": 3305, "army_b": None, "pawn_b": 3304,
        "count": 1, "pos_a": "last"}


def _plan(unlocked=(3304, 3305), armies=None):
    return sanitize_pawn_moves([SPEC], armies or _armies(), unlocked=unlocked,
                               pawn_names={3304: "Thợ Săn", 3305: "Lính Cường Nỏ"},
                               meet=lambda ar: CITY)


def test_no_holder_becomes_a_recruit_then_swap_proposal():
    out, notes = _plan()
    assert notes == [] and len(out) == 1
    m = out[0]
    assert m["op"] == "recruit_swap" and m["a"] == "F" and m["pawn_a"] == 3305
    assert m["pawn_b"] == 3304 and m["count"] == 1
    assert "chiêu mộ" in pawn_move_label(m) and "Thợ Săn" in pawn_move_label(m)
    assert m["spec"]["op"] == "swap"                      # confirm re-resolves the same request


def test_a_locked_type_is_refused_by_name():
    out, notes = _plan(unlocked=(3305,))
    assert out == [] and len(notes) == 1 and "Thợ Săn" in notes[0] and "mở khoá" in notes[0]


def test_when_a_holder_exists_it_is_a_plain_swap():
    armies = _armies() + [_army("H", "Đội 7", [3304, 3304])]
    out, _ = _plan(armies=armies)
    assert out[0]["op"] == "swap" and out[0]["b"] == "H"


class Acts:
    def __init__(self, armies, refuse=None):
        self.armies, self.calls, self.refuse = armies, [], refuse

    def get_player_armys(self):
        return self.armies

    def building_uid(self, bid):
        return "bar"

    def drill_pawn(self, bu, pawn_id, *, index=None, army_uid="", army_name=""):
        if self.refuse:
            raise RuntimeError(f"game/HD_DrillPawn: ecode.{self.refuse}")
        self.calls.append(("drill", pawn_id, army_uid, army_name))
        if not army_uid:                                   # a new army appears (pawn in training)
            self.armies.append(_army("NEW", army_name, [], drilling=[pawn_id]))

    def exchange_pawn_army(self, index, army_uid, u1, u2, army_uid2=None):
        self.calls.append(("ex", index, army_uid, u1, u2, army_uid2))


def _queued(tmp_path, armies=None):
    out, _ = _plan(armies=armies)
    q = PawnMoveQueue(tmp_path / "q.json")
    q.add({**out[0], "city": CITY, "cap": 9})
    return q


def test_recruits_into_a_roomy_idle_army_of_the_same_type_even_while_the_target_marches(tmp_path):
    q = _queued(tmp_path)
    acts = Acts(_armies())
    q.process(acts, lambda *a: None)
    assert acts.calls == [("drill", 3304, "S", "")]       # not the buffer, not the full army
    assert q.pending()                                     # waits for the training
    assert "S" in q.army_uids()                            # others leave the host alone


def test_swaps_after_the_hunter_is_trained(tmp_path):
    q = _queued(tmp_path)
    armies = _armies()
    acts = Acts(armies)
    q.process(acts, lambda *a: None)                       # ordered
    acts.calls.clear()
    q.process(acts, lambda *a: None)                       # still training: nothing
    assert acts.calls == []
    armies[1]["pawns"].append({"uid": "S9", "id": 3304, "lv": 1})
    armies[1]["drillPawns"] = []
    armies[0]["state"] = 0                                 # the target is home now
    q.process(acts, lambda *a: None)                       # becomes a plain swap
    q.process(acts, lambda *a: None)
    exs = [c for c in acts.calls if c[0] == "ex"]
    assert exs == [("ex", CITY, "F", "F8", "S9", "S")]     # the LAST IMP of Đội 5 <-> the hunter
    assert q.pending() == {}


def test_a_new_army_is_made_when_no_army_has_room(tmp_path):
    armies = [_army("F", "Đội 5", [3305] * 9), _army("N", "Nâng Cấp 1", [3305] * 4)]
    q = _queued(tmp_path, armies)
    acts = Acts(armies)
    q.process(acts, lambda *a: None)
    assert acts.calls and acts.calls[0][:3] == ("drill", 3304, "") and acts.calls[0][3].startswith("D")


def test_short_cereal_waits_and_keeps_the_job(tmp_path):
    q = _queued(tmp_path)
    acts = Acts(_armies(), refuse="500012")
    ev = []
    q.process(acts, lambda k, d=None: ev.append(k))
    assert q.pending() and "pawn_move_failed" not in ev     # kept, asked again later
