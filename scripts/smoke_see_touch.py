"""Manual smoke test: connect, screenshot, report what the game is showing.

    python scripts/smoke_see_touch.py

Proves the "see" (screencap) and device-awareness path end to end against the live emulator.
Does NOT tap by default — pass --tap X Y to test an input event.
"""

from __future__ import annotations

import argparse

from nta_agent.io.adb import DeviceManager


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="screen.png", help="where to save the screenshot")
    ap.add_argument("--tap", nargs=2, type=int, metavar=("X", "Y"), help="tap these coords")
    args = ap.parse_args()

    dm = DeviceManager.connect()
    print(f"device        : {dm.serial}")
    print(f"adb           : {dm.settings.adb_path}")
    print(f"game foreground: {dm.is_game_foreground()}")
    print(f"focus         : {dm.current_focus()}")

    path = dm.save_screenshot(args.out)
    print(f"screenshot    : {path} ({dm.screencap().size})")

    if args.tap:
        x, y = args.tap
        dm.tap(x, y)
        print(f"tapped        : ({x}, {y})")


if __name__ == "__main__":
    main()
