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
