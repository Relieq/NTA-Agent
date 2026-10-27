"""Between matches (the season ended / the next one opens later) the account has no game
server: the agent must WAIT for the match it applied to instead of crashing, and can apply
to a new one only on the player's request from the dashboard (live 2026-10-27)."""
import json

from nta_agent.runtime import lobby

NOW = 1793090000.0
RANKED_OPEN_MS = 1793152816075     # 2026-10-28 09:00
FREE_OPEN_MS = 1793325613318
# what the server sent live: proto defaults are omitted (state 0 = NONE, roomType 0 = free)
ROOMS = {"states": [{"time": FREE_OPEN_MS}, {"roomType": 2, "time": RANKED_OPEN_MS}],
         "canPlayRoomTypes": [2, 0]}
APPLIED = {"teamInfo": {"roomType": 2, "uid": "17319282", "userList": [{}]}}


def test_applied_to_ranked_waits_for_its_opening_time():
    st = lobby.lobby_status(ROOMS, APPLIED, NOW)
    assert st["state"] == "applied" and st["room_type"] == 2 and st["room_name"] == "Xếp hạng"
    assert st["opens_at"] == RANKED_OPEN_MS / 1000
    assert st["can_play"] == [2, 0]
    assert {r["room_type"]: r["opens_at"] for r in st["rooms"]} == {
        0: FREE_OPEN_MS / 1000, 2: RANKED_OPEN_MS / 1000}


def test_not_applied_when_the_server_says_so():
    team = {"teamInfo": {"uid": "1", "cancelApplySurplusTime": -1}}
    st = lobby.lobby_status(ROOMS, team, NOW)
    assert st["state"] == "not_applied" and st["opens_at"] is None


def test_next_check_is_just_after_the_opening_and_never_a_busy_loop():
    st = lobby.lobby_status(ROOMS, APPLIED, NOW)
    assert lobby.next_check_delay(st, NOW) == lobby.MAX_WAIT_S          # far away: capped
    near = lobby.next_check_delay(st, RANKED_OPEN_MS / 1000 - 100)
    assert near == 100 + lobby.AFTER_OPEN_S
    assert lobby.next_check_delay(st, RANKED_OPEN_MS / 1000 + 5) == lobby.MIN_WAIT_S   # opened: retry soon
    assert lobby.next_check_delay({"state": "not_applied"}, NOW) == lobby.MAX_WAIT_S


class _NoMatch(Exception):
    pass


class FakeClient:
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def request(self, route, body, **kw):
        self.calls.append((route, body))
        if self.fail:
            raise RuntimeError(self.fail)
        return {}


class FakeSession:
    def __init__(self, client):
        self.client, self.closed = client, False

    def close(self):
        self.closed = True


class Cfg:
    def __init__(self, tmp):
        self.lobby_path = tmp / "lobby.json"
        self.lobby_request_path = tmp / "lobby_request.json"


def _waiter(tmp, outcomes, client=None):
    """build() raises NoMatchError for each 'wait' outcome, then returns the session."""
    from nta_agent.io.api.session import NoMatchError
    events, sleeps = [], []
    client = client or FakeClient()
    seq = iter(outcomes)

    def build(cfg):
        o = next(seq)
        if o == "wait":
            raise NoMatchError(FakeSession(client), ROOMS, APPLIED)
        if o == "wait_free":
            raise NoMatchError(FakeSession(client), ROOMS,
                               {"teamInfo": {"cancelApplySurplusTime": -1}})
        return o
    got = lobby.wait_for_match(Cfg(tmp), build, on_event=lambda k, d=None: events.append((k, d)),
                               sleep=sleeps.append, clock=lambda: NOW, step_s=1e9)
    return got, events, sleeps, client


def test_waits_and_retries_until_the_match_is_open(tmp_path):
    got, events, sleeps, _ = _waiter(tmp_path, ["wait", "wait", "SESSION"])
    assert got == "SESSION"
    assert [k for k, _ in events].count("match_wait") == 1      # logged once, not every retry
    assert len(sleeps) == 2
    assert json.loads((tmp_path / "lobby.json").read_text(encoding="utf-8"))["state"] == "in_game"


def test_the_status_file_tells_the_dashboard_what_it_waits_for(tmp_path):
    from nta_agent.io.api.session import NoMatchError
    seen = {}

    def build(cfg):
        if not seen:
            seen["x"] = 1
            raise NoMatchError(FakeSession(FakeClient()), ROOMS, APPLIED)
        seen["file"] = json.loads((tmp_path / "lobby.json").read_text(encoding="utf-8"))
        return "S"
    lobby.wait_for_match(Cfg(tmp_path), build, sleep=lambda s: None, clock=lambda: NOW, step_s=1e9)
    assert seen["file"]["state"] == "applied" and seen["file"]["opens_at"] == RANKED_OPEN_MS / 1000


def test_applies_only_on_the_players_request_and_only_once(tmp_path):
    client = FakeClient()
    (tmp_path / "lobby_request.json").write_text(
        json.dumps({"seq": 7, "op": "apply", "room_type": 2}), encoding="utf-8")
    _waiter(tmp_path, ["wait_free", "wait", "S"], client=client)
    applies = [c for c in client.calls if c[0] == "lobby/HD_ApplyNewServer"]
    assert applies == [("lobby/HD_ApplyNewServer", {"roomType": 2})]   # seq 7 handled once


def test_never_applies_by_itself(tmp_path):
    client = FakeClient()
    _waiter(tmp_path, ["wait_free", "S"], client=client)
    assert not [c for c in client.calls if c[0] == "lobby/HD_ApplyNewServer"]


def test_a_room_type_the_server_does_not_offer_is_refused(tmp_path):
    client = FakeClient()
    (tmp_path / "lobby_request.json").write_text(
        json.dumps({"seq": 8, "op": "apply", "room_type": 1}), encoding="utf-8")
    _waiter(tmp_path, ["wait_free", "S"], client=client)
    assert not client.calls
    # the refusal is reported back while still waiting -> check via a run that stops after it
    from nta_agent.io.api.session import NoMatchError
    state = {}

    def build(cfg):
        if "n" in state:
            state["file"] = json.loads((tmp_path / "lobby.json").read_text(encoding="utf-8"))
            return "S"
        state["n"] = 1
        raise NoMatchError(FakeSession(client), ROOMS, {"teamInfo": {"cancelApplySurplusTime": -1}})
    (tmp_path / "lobby_request.json").write_text(
        json.dumps({"seq": 9, "op": "apply", "room_type": 1}), encoding="utf-8")
    lobby.wait_for_match(Cfg(tmp_path), build, sleep=lambda s: None, clock=lambda: NOW, step_s=1e9)
    assert state["file"]["apply"]["ok"] is False


def test_a_rejected_apply_is_reported_not_raised(tmp_path):
    client = FakeClient(fail="lobby/HD_ApplyNewServer: ecode.500000")
    (tmp_path / "lobby_request.json").write_text(
        json.dumps({"seq": 10, "op": "apply", "room_type": 0}), encoding="utf-8")
    got, events, _, _ = _waiter(tmp_path, ["wait_free", "S"], client=client)
    assert got == "S"
    assert any(k == "match_apply" and d["ok"] is False for k, d in events)


def test_the_lobby_session_is_closed_before_sleeping(tmp_path):
    from nta_agent.io.api.session import NoMatchError
    sessions = []

    def build(cfg):
        if not sessions:
            s = FakeSession(FakeClient())
            sessions.append(s)
            raise NoMatchError(s, ROOMS, APPLIED)
        return "S"
    lobby.wait_for_match(Cfg(tmp_path), build, sleep=lambda s: None, clock=lambda: NOW, step_s=1e9)
    assert sessions[0].closed


def test_an_old_click_is_not_applied_to_a_later_season(tmp_path):
    client = FakeClient()
    (tmp_path / "lobby_request.json").write_text(json.dumps(
        {"seq": 11, "op": "apply", "room_type": 2, "at": NOW - lobby.REQUEST_TTL_S - 1}),
        encoding="utf-8")
    _waiter(tmp_path, ["wait_free", "S"], client=client)
    assert not client.calls


def test_dashboard_writes_an_apply_request_only_while_the_agent_waits_for_one(tmp_path):
    from nta_agent.dashboard.server import lobby_command, read_lobby
    cfg = Cfg(tmp_path)
    assert lobby_command(cfg, {"room_type": 2})["ok"] is False          # no lobby status yet
    (tmp_path / "lobby.json").write_text(json.dumps(
        {"state": "applied", "room_type": 2, "can_play": [2, 0]}), encoding="utf-8")
    assert lobby_command(cfg, {"room_type": 2})["ok"] is False          # already applied
    (tmp_path / "lobby.json").write_text(json.dumps(
        {"state": "not_applied", "can_play": [2, 0]}), encoding="utf-8")
    assert lobby_command(cfg, {"room_type": 1})["ok"] is False          # not offered
    assert lobby_command(cfg, {"room_type": "x"})["ok"] is False
    assert lobby_command(cfg, {"room_type": 0})["ok"] is True
    req = json.loads((tmp_path / "lobby_request.json").read_text(encoding="utf-8"))
    assert req["op"] == "apply" and req["room_type"] == 0 and req["at"] > 0
    assert read_lobby(cfg)["apply_pending"] == 0
