"""The per-tick order in the runner that must not drift."""
from pathlib import Path


def test_a_new_game_is_checked_before_anything_that_acts_on_old_state():
    # 2026-10-14: dig.tick ran first and, on the stale dig of the previous match, blocked the
    # whole loop for minutes — check_new_game (which drops that state) never got its turn
    src = Path("nta_agent/runtime/runner.py").read_text(encoding="utf-8")
    body = src[src.index("    def on_tick(i, fired, state):"):]
    first = body.index("check_new_game(profile, cfg, state")
    for later in ("dig.tick, state", "run_services(", "alerts.tick"):
        assert first < body.index(later), later
