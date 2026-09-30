"""Detect a fresh game (a NEW main city, e.g. re-created after capture) and reset the
state bound to the old armies/cells — so nothing chases armies that no longer exist.

``army.home_city`` in the profile records which main city the uid/cell-bound fields
belong to. First sighting just records it; a different main city later means a new
game: clear the strike goal, army uids (group/roles/presets/logistics), the pending
fort queue and fort accept/reject decisions (all old-map cells), the match-bound config
(leveling, logistics, revive, notes) and the files that name old equips/armies/cells.
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


def _drop(path) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def _reset_match_files(cfg) -> None:
    """Files bound to the old match's equips / armies / cells: emptied or removed so the
    new match starts clean (forge targets name old equip uids, the equip choice names an
    equip that no longer exists, the dig/buffers point at old armies and cells...)."""
    def p(name, fallback=None):
        v = getattr(cfg, name, None)
        return v if v is not None else fallback
    sibling = getattr(cfg, "commands_path", None)
    if p("forge_targets_path") is not None:
        _write_json(cfg.forge_targets_path, {})
    if sibling is not None:
        _write_json(Path(sibling).with_name("equip_sync.json"), {})
        _drop(Path(sibling).with_name("pending_dismissals.json"))
    for name in ("dig_state_path", "dig_request_path", "buffers_path", "spare_advice_path",
                 "pending_renames_path"):
        if p(name) is not None:
            _drop(getattr(cfg, name))
    if p("brain_advice_path") is not None:
        _write_json(cfg.brain_advice_path, [])
    if p("composition_status_path") is not None:
        _write_json(cfg.composition_status_path, {"active": False})


def check_new_game(profile, cfg, state, on_event=None, services=()) -> bool:
    """Returns True if a new game was detected and stale state was reset.
    ``services``: objects with an optional ``reset_for_new_game()`` (in-memory state)."""
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
    _reset_match_files(cfg)
    for svc in services or ():
        hook = getattr(svc, "reset_for_new_game", None)
        if callable(hook):
            try:
                hook()
            except Exception:
                pass  # one service failing must not leave the rest un-reset
    reload_into(profile, cfg.profile_path)
    if on_event:
        on_event("new_game_reset", {"from": home, "to": main, "cleared": cleared})
    return True
