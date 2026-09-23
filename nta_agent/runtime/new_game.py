"""Detect a fresh game (a NEW main city, e.g. re-created after capture) and reset the
state bound to the old armies/cells — so nothing chases armies that no longer exist.

``army.home_city`` in the profile records which main city the uid/cell-bound fields
belong to. First sighting just records it; a different main city later means a new
game: clear the strike goal, army uids (group/roles/presets/logistics), the pending
fort queue and fort accept/reject decisions (all old-map cells).
"""
from __future__ import annotations

import json
from pathlib import Path

from nta_agent.execution.profile import (
    load_profile,
    reload_into,
    reset_for_new_game,
    save_profile,
)


def _write_json(path, value) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value), encoding="utf-8")


def check_new_game(profile, cfg, state, on_event=None) -> bool:
    """Returns True if a new game was detected and stale state was reset."""
    main = int(getattr(state, "main_city_index", 0) or 0)
    if not main:
        return False
    home = int((profile.army or {}).get("home_city") or 0)
    if home == main:
        return False
    if not home:  # first sighting: remember which city this profile belongs to
        disk = load_profile(cfg.profile_path)
        disk.army["home_city"] = main
        save_profile(disk, cfg.profile_path)
        reload_into(profile, cfg.profile_path)
        return False
    cleared = reset_for_new_game(cfg.profile_path, main)
    _write_json(cfg.pending_forts_path, [])
    _write_json(cfg.fort_decisions_path, {})
    reload_into(profile, cfg.profile_path)
    if on_event:
        on_event("new_game_reset", {"from": home, "to": main, "cleared": cleared})
    return True
