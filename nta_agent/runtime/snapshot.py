"""Serialize GameState to a stable, JSON-safe snapshot for the dashboard."""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from pathlib import Path

from nta_agent.state.schema import GameState


def _player_subset(raw: dict) -> dict:
    player = (raw or {}).get("player", {}) or {}
    slots = player.get("pawnSlots") or {}
    pawn_ids = [v["id"] for v in slots.values() if isinstance(v, dict) and v.get("id")]
    return {
        "guide_tasks": len(player.get("guideTasks") or []),
        "other_tasks": len(player.get("otherTasks") or []),
        "today_tasks": len(player.get("todayTasks") or []),
        "pawn_slots": pawn_ids,
    }


def state_to_dict(state: GameState) -> dict:
    from nta_agent.execution.territory import build_territory
    mw = int(getattr(state, "map_width", 0) or 0) or 600
    terr = build_territory(state, map_width=mw)
    return {
        "source": state.source,
        "updated_at": state.updated_at,
        "uid": state.user.uid,
        "main_city_index": state.main_city_index,
        "room_type": state.room_type,
        "resources": asdict(state.resources),
        "builds": [{"index": b.index, "id": b.id, "lv": b.lv, "uid": b.uid}
                   for b in state.builds],
        "marches": len(state.marches),
        "areas": len(state.areas),
        "build_queue": state.build_queue,
        "build_queue_slots": state.build_queue_slots,
        "production": state.production,
        "granary_cap": state.granary_cap,
        "warehouse_cap": state.warehouse_cap,
        "player": _player_subset(state.raw),
        "forts": [{"index": f.index, "auto_support": f.auto_support} for f in terr.forts],
        "garrisons": terr.garrisons,
        "map_width": terr.map_width,
    }


def write_snapshot(state: GameState, path: Path) -> dict:
    d = state_to_dict(state)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    # Windows refuses to replace a file another process (the dashboard) has open for
    # reading (WinError 5 / PermissionError): retry briefly instead of losing the tick.
    for attempt in range(5):
        try:
            os.replace(tmp, path)
            break
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05 * (attempt + 1))
    return d
