"""Serialize GameState to a stable, JSON-safe snapshot for the dashboard."""
from __future__ import annotations

import json
import os
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
    return {
        "source": state.source,
        "updated_at": state.updated_at,
        "uid": state.user.uid,
        "main_city_index": state.main_city_index,
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
    }


def write_snapshot(state: GameState, path: Path) -> dict:
    d = state_to_dict(state)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return d
