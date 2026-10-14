"""Start the emulator only while a token refresh needs it.

The account token is minted by Google sign-in INSIDE the game app, so the emulator is still
needed when the token chain breaks (the player logged in elsewhere). Until now the player had
to start it by hand. This module starts it through LDPlayer's console (``ldconsole``), waits
until adb sees it and the system has booted, and quits it again afterwards — but ONLY if it
started it: an emulator that is already running (the player is using it) is never touched.
"""
from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path


def index_from_serial(serial: str) -> int:
    """LDPlayer instance index from the adb serial (emulator-5554 / 127.0.0.1:5555 = 0)."""
    m = re.fullmatch(r"emulator-(\d+)", serial or "")
    if m:
        return max(0, (int(m.group(1)) - 5554) // 2)
    m = re.fullmatch(r"[\d.]+:(\d+)", serial or "")
    if m:
        return max(0, (int(m.group(1)) - 5555) // 2)
    return 0


def find_console(adb_path: str) -> str | None:
    """``ldconsole.exe`` (LDPlayer 9/14) or ``dnconsole.exe`` next to adb.exe."""
    from nta_agent import settings
    override = settings.get("ldconsole_path")
    if override and Path(override).is_file():
        return str(override)
    folder = Path(str(adb_path or "")).parent
    for name in ("ldconsole.exe", "dnconsole.exe"):
        if (folder / name).is_file():
            return str(folder / name)
    return None


def _run_console(console: str):
    def run(args, timeout: float = 60) -> str:
        proc = subprocess.run([console, *args], capture_output=True, timeout=timeout,
                              cwd=str(Path(console).parent))
        return proc.stdout.decode("utf-8", "ignore")
    return run


class Emulator:
    def __init__(self, console: str, index: int = 0, runner=None, sleep=time.sleep,
                 clock=time.monotonic, ready_timeout: float = 240.0, poll: float = 3.0):
        self.console, self.index = console, int(index)
        self._run = runner or _run_console(console)
        self._sleep, self._clock = sleep, clock
        self.ready_timeout, self.poll = ready_timeout, poll

    def _ld(self, *args, timeout: float = 60) -> str:
        return self._run(list(args), timeout=timeout)

    def is_running(self) -> bool:
        return self._ld("isrunning", "--index", str(self.index)).strip().lower() == "running"

    def launch(self) -> None:
        self._ld("launch", "--index", str(self.index))

    def quit(self) -> None:
        self._ld("quit", "--index", str(self.index))

    def wait_ready(self, dm) -> bool:
        """adb lists the device AND the system finished booting."""
        end = self._clock() + self.ready_timeout
        while True:
            try:
                if dm.serial in dm.devices() and dm.shell("getprop sys.boot_completed").strip() == "1":
                    return True
            except Exception:
                pass
            if self._clock() >= end:
                return False
            self._sleep(self.poll)


class EmulatorPower:
    """Bring the emulator up for a token refresh and put it back as it was."""

    def __init__(self, emulator: Emulator):
        self.emu = emulator
        self._started = False

    def ensure_up(self, dm) -> bool:
        """True when WE started it (so ``shutdown`` will stop it), False when it was already
        up. Raises RuntimeError when it does not come up in time."""
        try:
            if dm.serial in dm.devices():
                return False
        except Exception:
            pass
        started = False
        if not self.emu.is_running():
            self.emu.launch()
            started = True
        self._started = started
        if not self.emu.wait_ready(dm):
            self.shutdown()
            raise RuntimeError("giả lập không sẵn sàng (adb chưa thấy thiết bị) — thôi")
        return started

    def shutdown(self) -> None:
        if self._started:
            self._started = False
            try:
                self.emu.quit()
            except Exception:
                pass


def default_power(adb_path: str, serial: str) -> EmulatorPower | None:
    """The launcher the agent uses, or None when switched off (Settings ``auto_emulator``=0)
    or when LDPlayer's console cannot be found."""
    from nta_agent import settings
    if str(settings.get("auto_emulator") or "1").strip().lower() in ("0", "false", "no", "off", "tắt"):
        return None
    console = find_console(adb_path)
    if not console:
        return None
    index = settings.get("ldplayer_index")
    idx = int(index) if str(index or "").isdigit() else index_from_serial(serial)
    return EmulatorPower(Emulator(console, idx))
