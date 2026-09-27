"""read_account_token parsing, with a fake device that stages a synthetic db."""

import sqlite3
from pathlib import Path

from nta_agent.io.bootstrap import read_account_token


class FakeDM:
    def __init__(self, token: str):
        self.token = token

    def su(self, command: str, timeout: float = 30) -> str:
        return ""

    def pull(self, remote: str, local: str, timeout: float = 60) -> str:
        p = Path(local)
        if p.exists():
            p.unlink()
        con = sqlite3.connect(local)
        con.execute("CREATE TABLE data (key TEXT PRIMARY KEY, value TEXT)")
        con.execute("INSERT INTO data VALUES (?, ?)", ("slg_account_token", self.token))
        con.execute("INSERT INTO data VALUES (?, ?)", ("__slg_lang__", "vi"))
        con.commit()
        con.close()
        return local


def test_read_account_token_extracts_key():
    tok = "e3e836e696445f2814c89ea39083338a15c6407b87ad3e84e885ccf39fbfb08a"
    assert read_account_token(FakeDM(tok)) == tok


def test_read_account_token_missing_returns_empty():
    class NoTokenDM(FakeDM):
        def pull(self, remote, local, timeout=60):
            p = Path(local)
            if p.exists():
                p.unlink()
            con = sqlite3.connect(local)
            con.execute("CREATE TABLE data (key TEXT, value TEXT)")
            con.commit()
            con.close()
            return local

    assert read_account_token(NoTokenDM("")) == ""


def test_refresher_first_reuses_the_token_the_game_already_has(tmp_path, monkeypatch):
    # user 2026-09-27: after logging in to the game in the emulator (then quitting),
    # the agent should pick that token up by itself — no Setup step, no app restart
    from nta_agent.io import bootstrap
    tok = tmp_path / "t.txt"
    tok.write_text("SPENT" + "x" * 40)
    oauth = []
    monkeypatch.setattr(bootstrap, "read_account_token", lambda dm, *a, **k: "FRESH" + "y" * 40)
    monkeypatch.setattr(bootstrap, "refresh_token_via_app", lambda dm, p, **k: oauth.append(1))
    refresh = bootstrap.make_token_refresher(object(), tok)
    assert refresh() is True and tok.read_text().startswith("FRESH") and oauth == []
    # the game's token is the same one (already tried/spent) -> the OAuth flow
    assert refresh() is True and oauth == [1]


def test_refresher_goes_to_oauth_when_the_game_token_is_ours(tmp_path, monkeypatch):
    from nta_agent.io import bootstrap
    tok = tmp_path / "t.txt"
    tok.write_text("SAME" + "z" * 40)
    oauth = []
    monkeypatch.setattr(bootstrap, "read_account_token", lambda dm, *a, **k: "SAME" + "z" * 40)
    monkeypatch.setattr(bootstrap, "refresh_token_via_app", lambda dm, p, **k: oauth.append(1))
    assert bootstrap.make_token_refresher(object(), tok)() is True and oauth == [1]


def test_login_tries_the_refresher_twice(monkeypatch):
    # 1st refresh (game token) may itself be spent -> a 2nd refresh (OAuth) is tried
    from nta_agent.io.api import session as sess
    from nta_agent.io.api.client import ApiError
    s = sess.GameSession.__new__(sess.GameSession)
    s._distinct_id, s._login_opts = "", {}
    tries = iter([ApiError("x: ecode.500002"), ApiError("x: ecode.500002"), {"ok": 1}])

    def fake_try(tok, timeout=15):
        r = next(tries)
        if isinstance(r, Exception):
            raise r
        return r
    s._try_login = fake_try
    calls = []
    s.token_refresher = lambda: calls.append(1) or True
    assert s.login() == {"ok": 1} and len(calls) == 2
