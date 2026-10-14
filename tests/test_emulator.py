"""Start the emulator only for as long as a token refresh needs it (player 2026-10-14: 'tránh việc
tôi cứ phải bật trình giả lập lên'). ldconsole is injected so nothing real is started."""
import pytest

from nta_agent.io import bootstrap
from nta_agent.io.emulator import Emulator, EmulatorPower, find_console, index_from_serial


class Console:
    """A fake ldconsole: remembers calls and the running state."""

    def __init__(self, running=False):
        self.calls = []
        self.running = running

    def __call__(self, args, timeout=60):
        self.calls.append(tuple(args))
        if args[0] == "isrunning":
            return "running" if self.running else "stop"
        if args[0] == "launch":
            self.running = True
        if args[0] == "quit":
            self.running = False
        return ""


class DM:
    def __init__(self, console, serial="emulator-5554", boot_after=0):
        self.console, self._serial, self.boot_after, self.polls = console, serial, boot_after, 0

    @property
    def serial(self):
        return self._serial

    def devices(self):
        self.polls += 1
        return [self._serial] if self.console.running and self.polls > self.boot_after else []

    def shell(self, cmd, timeout=30):
        return "1\n" if "boot_completed" in cmd else ""


def _emu(console, **kw):
    return Emulator("ldconsole.exe", index=0, runner=console, sleep=lambda s: None, **kw)


def test_index_follows_the_adb_serial():
    assert index_from_serial("emulator-5554") == 0
    assert index_from_serial("emulator-5556") == 1
    assert index_from_serial("127.0.0.1:5555") == 0
    assert index_from_serial("127.0.0.1:5557") == 1
    assert index_from_serial("weird") == 0


def test_find_console_looks_next_to_adb(tmp_path):
    (tmp_path / "adb.exe").write_bytes(b"")
    (tmp_path / "ldconsole.exe").write_bytes(b"")
    assert find_console(str(tmp_path / "adb.exe")).endswith("ldconsole.exe")
    assert find_console(str(tmp_path / "missing" / "adb.exe")) is None


def test_already_running_is_left_alone_and_never_quit():
    con = Console(running=True)
    power = EmulatorPower(_emu(con))
    assert power.ensure_up(DM(con)) is False
    power.shutdown()
    assert not [c for c in con.calls if c[0] in ("launch", "quit")]


def test_a_stopped_emulator_is_launched_waited_for_and_quit_afterwards():
    con = Console(running=False)
    power = EmulatorPower(_emu(con))
    dm = DM(con, boot_after=2)
    assert power.ensure_up(dm) is True
    assert ("launch", "--index", "0") in con.calls and dm.polls >= 3   # waited for adb to list it
    power.shutdown()
    assert con.calls[-1] == ("quit", "--index", "0") and con.running is False


def test_an_emulator_that_never_comes_up_is_given_up_and_quit():
    con = Console(running=False)
    power = EmulatorPower(_emu(con, ready_timeout=0))
    dm = DM(con, boot_after=10 ** 6)
    with pytest.raises(RuntimeError):
        power.ensure_up(dm)
    assert con.calls[-1] == ("quit", "--index", "0")


def test_the_refresher_brings_the_emulator_up_and_takes_it_down_again(tmp_path, monkeypatch):
    con = Console(running=False)
    power = EmulatorPower(_emu(con))
    dm = DM(con)
    tok = tmp_path / "t.txt"
    tok.write_text("SPENT" + "x" * 40)
    seen = {}

    def read(d, *a, **k):
        seen["running_during"] = con.running
        return "FRESH" + "y" * 40
    monkeypatch.setattr(bootstrap, "read_account_token", read)
    assert bootstrap.make_token_refresher(dm, tok, power=power)() is True
    assert seen["running_during"] is True and con.running is False       # up only while needed
    assert tok.read_text().startswith("FRESH")


def test_the_refresher_without_a_launcher_behaves_as_before(tmp_path, monkeypatch):
    tok = tmp_path / "t.txt"
    tok.write_text("SPENT" + "x" * 40)
    monkeypatch.setattr(bootstrap, "read_account_token", lambda d, *a, **k: "FRESH" + "y" * 40)
    assert bootstrap.make_token_refresher(object(), tok)() is True


def test_a_launch_failure_makes_the_refresh_fail_cleanly(tmp_path, monkeypatch):
    con = Console(running=False)
    power = EmulatorPower(_emu(con, ready_timeout=0))
    tok = tmp_path / "t.txt"
    tok.write_text("SPENT" + "x" * 40)
    monkeypatch.setattr(bootstrap, "read_account_token", lambda d, *a, **k: "FRESH" + "y" * 40)
    assert bootstrap.make_token_refresher(DM(con, boot_after=10 ** 6), tok, power=power)() is False
    assert con.running is False                                          # nothing left running
