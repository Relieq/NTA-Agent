"""Renames wait for the army to be idle and use its CURRENT index (live 2026-09-25:
one-shot rename commands failed with 500036 'in battle' / 500011 'army not found'
for a marching army's stale index, and nothing retried)."""
from nta_agent.runtime.rename_queue import RenameQueue


class Acts:
    def __init__(self, armies, fail=None):
        self.armies = armies
        self.fail = dict(fail or {})   # uid -> exception message (consumed once)
        self.calls = []

    def get_player_armys(self):
        return self.armies

    def rename_army(self, index, uid, name):
        self.calls.append((index, uid, name))
        if uid in self.fail:
            raise RuntimeError(self.fail.pop(uid))
        next(a for a in self.armies if a["uid"] == uid)["name"] = name


def _army(uid, name="D1", index=5, state=0):
    return {"uid": uid, "name": name, "index": index, "state": state}


def test_waits_for_an_idle_army_and_uses_its_current_index(tmp_path):
    q = RenameQueue(tmp_path / "pr.json")
    q.add("a", "D5")
    army = _army("a", index=5, state=2)          # fighting
    acts, events = Acts([army]), []
    q.process(acts, lambda k, d: events.append((k, d)))
    assert acts.calls == []
    army.update(state=0, index=77)               # back home, moved cell
    q.process(acts, lambda k, d: events.append((k, d)))
    assert acts.calls == [(77, "a", "D5")]
    assert ("rename_done", {"uid": "a", "name": "D5"}) in events
    assert q.pending() == {}


def test_transient_error_retries_later_permanent_error_drops(tmp_path):
    q = RenameQueue(tmp_path / "pr.json", retry_ticks=2)
    q.add("a", "D5")
    q.add("b", "Đội 2")
    acts = Acts([_army("a"), _army("b")],
                fail={"a": "HD_ModifyAmryName: ecode.500036", "b": "HD_ModifyAmryName: ecode.500061"})
    events = []
    q.process(acts, lambda k, d: events.append((k, d)))
    assert set(q.pending()) == {"a"}                       # b dropped (name taken)
    assert any(k == "rename_failed" and d["uid"] == "b" for k, d in events)
    q.process(acts, lambda k, d: None)                      # still waiting (retry_ticks)
    q.process(acts, lambda k, d: None)
    q.process(acts, lambda k, d: None)
    assert q.pending() == {} and acts.calls[-1] == (5, "a", "D5")


def test_persists_across_restarts_and_drops_gone_armies(tmp_path):
    p = tmp_path / "pr.json"
    RenameQueue(p).add("ghost", "X")
    q = RenameQueue(p, give_up_missing=2)
    assert "ghost" in q.pending()
    events = []
    for _ in range(2):
        q.process(Acts([]), lambda k, d: events.append(k))
    assert q.pending() == {} and "rename_failed" in events


def test_already_named_is_done_without_a_request(tmp_path):
    q = RenameQueue(tmp_path / "pr.json")
    q.add("a", "D5")
    acts = Acts([_army("a", name="D5")])
    q.process(acts, lambda k, d: None)
    assert acts.calls == [] and q.pending() == {}
