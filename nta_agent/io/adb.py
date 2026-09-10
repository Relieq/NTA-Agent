"""DeviceManager — the agent's "eyes and hands" on the emulator via ADB.

Thin, dependency-light wrapper that shells out to the (bundled) adb binary. Shelling out
rather than using a Python adb client keeps us on the exact adb build BlueStacks ships, which
avoids server/protocol version mismatches.

The two primitives everything else is built on:
  * screencap()  -> a PIL image of the current screen  ("see")
  * tap()/swipe() -> input events                        ("touch")
"""

from __future__ import annotations

import io
import subprocess
import time
from dataclasses import dataclass

from PIL import Image

from nta_agent.config import Settings, load_settings


class AdbError(RuntimeError):
    """Raised when an adb command fails after retries."""


@dataclass
class DeviceManager:
    settings: Settings
    _serial: str | None = None

    # ---- lifecycle -----------------------------------------------------------------

    @classmethod
    def connect(cls, settings: Settings | None = None) -> "DeviceManager":
        settings = settings or load_settings()
        dm = cls(settings=settings)
        dm._ensure_connected()
        return dm

    def _ensure_connected(self) -> None:
        """Resolve a usable serial, connecting over TCP if configured."""
        if self.settings.serial and ":" in self.settings.serial:
            # e.g. "127.0.0.1:5555" — connect is idempotent.
            self._raw(["connect", self.settings.serial], timeout=10)
        serial = self.settings.serial or self._first_device()
        if not serial:
            raise AdbError("no adb device found — is BlueStacks running with ADB enabled?")
        self._serial = serial

    def _first_device(self) -> str | None:
        out = self._raw(["devices"], timeout=10).decode("utf-8", "ignore")
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) == 2 and parts[1] == "device":
                return parts[0]
        return None

    @property
    def serial(self) -> str:
        if not self._serial:
            self._ensure_connected()
        return self._serial  # type: ignore[return-value]

    # ---- low-level command runners -------------------------------------------------

    def _raw(self, args: list[str], timeout: float = 30) -> bytes:
        """Run adb without a target device (connect/devices)."""
        proc = subprocess.run(
            [self.settings.adb_path, *args],
            capture_output=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            raise AdbError(f"adb {' '.join(args)} failed: {proc.stderr.decode('utf-8', 'ignore')}")
        return proc.stdout

    def _adb(self, args: list[str], timeout: float = 30) -> bytes:
        """Run adb against the resolved device; returns raw stdout bytes."""
        proc = subprocess.run(
            [self.settings.adb_path, "-s", self.serial, *args],
            capture_output=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            raise AdbError(f"adb {' '.join(args)} failed: {proc.stderr.decode('utf-8', 'ignore')}")
        return proc.stdout

    def shell(self, command: str, timeout: float = 30) -> str:
        """Run a shell command on the device, returning decoded stdout."""
        return self._adb(["shell", command], timeout=timeout).decode("utf-8", "ignore")

    # ---- "see" ---------------------------------------------------------------------

    def screencap(self, retries: int = 2) -> Image.Image:
        """Capture the screen as a PIL image.

        Uses ``exec-out screencap -p`` so the PNG bytes stream back untouched (plain
        ``shell`` mangles them via CRLF translation).
        """
        last_err: Exception | None = None
        for attempt in range(retries + 1):
            try:
                png = self._adb(["exec-out", "screencap", "-p"], timeout=20)
                if png:
                    return Image.open(io.BytesIO(png)).convert("RGB")
                last_err = AdbError("empty screencap")
            except (AdbError, subprocess.TimeoutExpired, OSError) as e:
                last_err = e
            if attempt < retries:
                time.sleep(0.5)
                try:  # emulator may have hiccuped; re-resolve the device
                    self._ensure_connected()
                except AdbError:
                    pass
        raise AdbError(f"screencap failed after {retries + 1} attempts: {last_err}")

    def save_screenshot(self, path: str) -> str:
        self.screencap().save(path)
        return path

    # ---- "touch" -------------------------------------------------------------------

    def tap(self, x: int, y: int) -> None:
        self.shell(f"input tap {int(x)} {int(y)}")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self.shell(f"input swipe {int(x1)} {int(y1)} {int(x2)} {int(y2)} {int(duration_ms)}")

    def input_text(self, text: str) -> None:
        # adb input text uses %s for spaces and cannot handle arbitrary unicode reliably.
        safe = text.replace(" ", "%s")
        self.shell(f"input text {safe}")

    def keyevent(self, keycode: int | str) -> None:
        self.shell(f"input keyevent {keycode}")

    def back(self) -> None:
        self.keyevent(4)

    def home(self) -> None:
        self.keyevent(3)

    # ---- game awareness ------------------------------------------------------------

    def current_focus(self) -> str:
        out = self.shell("dumpsys window | grep -E 'mCurrentFocus'")
        return out.strip()

    def is_game_foreground(self) -> bool:
        return self.settings.game_package in self.current_focus()

    def launch_game(self) -> None:
        self.shell(f"monkey -p {self.settings.game_package} -c android.intent.category.LAUNCHER 1")
