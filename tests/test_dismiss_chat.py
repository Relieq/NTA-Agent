"""Dismissing armies / pawns on the player's request: the brain only PROPOSES (like
renames), the player confirms on the dashboard, then a queue waits for the army to be
idle and sends the dismissals (irreversible, so nothing runs without the confirm)."""
from __future__ import annotations

import json
from pathlib import Path

from nta_agent.brain.guard import sanitize_dismissals
from nta_agent.dashboard.server import confirm_dismissals, handle_chat
from nta_agent.runtime.commands import read_pending
from nta_agent.runtime.config import RuntimeConfig
from nta_agent.runtime.dismiss_queue import DismissQueue


def _army(uid, name, pawns, state=0, index=100):
    return {"uid": uid, "name": name, "index": index, "state": state,
            "pawns": [{"uid": f"{uid}{i}", "id": pid, "lv": lv} for i, (pid, lv) in enumerate(pawns)]}


ARMIES = [_army("A", "Đội 1", [(3305, 3), (3305, 1), (3202, 2), (3305, 2)]),
          _army("B", "D7", [(3201, 1)] * 3, state=1)]


# ---- guard: what may be proposed --------------------------------------------------
def test_dismiss_lowest_level_pawns_of_a_type():
    out, _ = sanitize_dismissals([{"uid": "A", "scope": "pawns", "pawn_id": 3305, "count": 2}],
                                     ARMIES)
    (d,) = out
    assert d["scope"] == "pawns" and d["count"] == 2
    assert d["pawn_uids"] == ["A1", "A3"]            # the two lowest-level 3305 (lv1, lv2)


def test_whole_army_and_limits():
    out, _ = sanitize_dismissals([{"uid": "B", "scope": "army"}], ARMIES)
    assert out[0]["scope"] == "army" and out[0]["count"] == 3
    # unknown army / count beyond what exists / zero are dropped or clamped
    out, _ = sanitize_dismissals([{"uid": "ZZ", "scope": "army"},
                                  {"uid": "A", "scope": "pawns", "pawn_id": 3305, "count": 9},
                                  {"uid": "A", "scope": "pawns", "pawn_id": 3101, "count": 1}],
                                 ARMIES)
    assert [(d["uid"], d["count"]) for d in out] == [("A", 3)]


def test_heroes_are_never_dismissed():
    armies = [{"uid": "H", "name": "Đội H", "index": 1, "state": 0, "pawns": [
        {"uid": "h0", "id": 3101, "lv": 1, "hero": True}, {"uid": "h1", "id": 3101, "lv": 1}]}]
    out, notes = sanitize_dismissals([{"uid": "H", "scope": "army"}], armies)
    assert out == [] and any("tướng" in n for n in notes)
    out, _ = sanitize_dismissals([{"uid": "H", "scope": "pawns", "count": 2}], armies)
    assert out[0]["pawn_uids"] == ["h1"]


# ---- queue: wait for idle, then send ------------------------------------------------
class Acts:
    def __init__(self, armies):
        self.armies, self.calls = armies, []

    def get_player_armys(self):
        return self.armies

    def dismiss_army(self, index, uid, pawn_id=0):
        self.calls.append(("army", index, uid, pawn_id))

    def dismiss_pawn(self, index, uid, pawn_uid):
        self.calls.append(("pawn", index, uid, pawn_uid))


def test_queue_waits_for_an_idle_army_then_dismisses(tmp_path):
    q = DismissQueue(tmp_path / "q.json")
    q.add("B", "army", [])
    acts, ev = Acts([dict(a) for a in ARMIES]), []
    q.process(acts, lambda k, d: ev.append((k, d)))
    assert acts.calls == []                                   # B is marching
    acts.armies[1]["state"] = 0
    q.process(acts, lambda k, d: ev.append((k, d)))
    assert acts.calls == [("army", 100, "B", 0)] and ev[-1][0] == "dismiss_done"
    assert q.pending() == {}


def test_queue_dismisses_pawns_a_few_per_tick_and_survives_restart(tmp_path):
    p = tmp_path / "q.json"
    DismissQueue(p).add("A", "pawns", ["A0", "A1", "A2", "A3"])
    acts = Acts([dict(a) for a in ARMIES])
    DismissQueue(p).process(acts, lambda *a: None)            # a new instance = a restart
    assert [c[3] for c in acts.calls] == ["A0", "A1", "A2"]    # at most 3 per tick
    acts.armies[0]["pawns"] = [p for p in acts.armies[0]["pawns"] if p["uid"] == "A3"]
    DismissQueue(p).process(acts, lambda *a: None)
    assert acts.calls[-1] == ("pawn", 100, "A", "A3") and DismissQueue(p).pending() == {}


def test_queue_drops_a_permanent_refusal_and_reports_it(tmp_path):
    class Refuse(Acts):
        def dismiss_army(self, *a):
            raise RuntimeError("game/HD_DismissArmy: ecode.500099")
    q = DismissQueue(tmp_path / "q.json")
    q.add("A", "army", [])
    ev = []
    q.process(Refuse([dict(a) for a in ARMIES]), lambda k, d: ev.append(k))
    assert ev == ["dismiss_failed"] and q.pending() == {}


# ---- chat: propose, then confirm --------------------------------------------------
def _cfg(tmp_path):
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)
    Path(cfg.armies_path).write_text(json.dumps(ARMIES, ensure_ascii=False), encoding="utf-8")
    return cfg


def test_chat_proposes_a_dismissal_without_executing(tmp_path):
    cfg = _cfg(tmp_path)

    def propose(digest, profile, instruction=None, history=None):
        return {"army_dismissals": [{"uid": "A", "scope": "pawns", "pawn_id": 3305, "count": 1}]}
    out = handle_chat(cfg, "giải tán 1 lính IMP thấp cấp nhất của Đội 1", history=[],
                      propose=propose)
    assert out["ok"] and out["needs_confirm"] is True
    (d,) = out["dismissals"]
    assert d["name"] == "Đội 1" and d["count"] == 1 and d["scope"] == "pawns"
    assert not [c for c in read_pending(cfg.commands_path, cfg.commands_done_path)
                if c.get("action") == "dismiss"]               # nothing queued yet


def test_confirm_revalidates_and_queues_the_command(tmp_path):
    cfg = _cfg(tmp_path)
    r = confirm_dismissals(cfg, [{"uid": "A", "scope": "pawns", "pawn_id": 3305, "count": 2},
                                 {"uid": "GONE", "scope": "army"}])
    assert r["ok"] and len(r["queued"]) == 1
    (cmd,) = [c for c in read_pending(cfg.commands_path, cfg.commands_done_path)
              if c.get("action") == "dismiss"]
    assert cmd["uid"] == "A" and cmd["scope"] == "pawns" and cmd["pawn_uids"] == ["A1", "A3"]


def test_decision_service_hands_the_command_to_the_queue(tmp_path):
    from nta_agent.runtime.decision_service import DecisionService
    cfg = _cfg(tmp_path)
    svc = DecisionService.__new__(DecisionService)
    svc.actions, svc.profile = Acts([]), None
    svc.dismissals = DismissQueue(tmp_path / "dq.json")
    svc._execute({"action": "dismiss", "uid": "A", "scope": "army", "pawn_uids": []})
    assert svc.dismissals.pending()["A"]["scope"] == "army"
    assert cfg  # (cfg only for the armies file; unused here)


def test_the_autonomous_brain_loop_can_never_dismiss():
    # army_dismissals is only read by the CHAT path (proposal -> dashboard confirm);
    # the background brain's edits go through sanitize_edits, which ignores the key
    from nta_agent.brain.guard import sanitize_edits
    from nta_agent.execution.profile import load_profile
    out = sanitize_edits({"army_dismissals": [{"uid": "A", "scope": "army"}],
                          "occupy": {"max_loss": 5}}, load_profile("nonexistent"), {"A"})
    assert "army_dismissals" not in out
