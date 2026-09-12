"""Detect reserved ceri decisions (unlock pawn/policy/equip) pending a human pick."""
from __future__ import annotations

from dataclasses import dataclass

# player slot-map field -> (StudyType tp, text table). tp verified in client.
TRACKS = {
    "pawnSlots": (2, "pawnText"),
    "policySlots": (1, "policyText"),
    "equipSlots": (3, "equipText"),
}
_TRACK_NAME = {"pawnSlots": "pawn", "policySlots": "policy", "equipSlots": "equip"}


@dataclass
class Decision:
    track: str
    tp: int
    slot_key: str
    lv: int
    reset_count: int
    options: list[dict]


def _name(text_table: dict, value: int) -> str:
    row = text_table.get(f"name_{value}") or {}
    return row.get("vi") or row.get("en") or f"#{value}"


def pending_decisions(state, config) -> list[Decision]:
    player = (state.raw or {}).get("player", {}) or {}
    ceri = config.table("ceri")
    out: list[Decision] = []
    for slot_field, (tp, text_name) in TRACKS.items():
        text_table = config.table(text_name)
        slots = player.get(slot_field) or {}
        for slot_key, slot in slots.items():
            if not isinstance(slot, dict):
                continue
            select_ids = slot.get("selectIds") or []
            if (slot.get("id") or 0) > 0 or not select_ids:
                continue  # already chosen, or nothing offered -> not pending
            options = []
            for cid in select_ids:
                value = (ceri.get(cid) or {}).get("value", 0)
                options.append({"ceri_id": cid, "value": value,
                                "name": _name(text_table, value)})
            out.append(Decision(track=_TRACK_NAME[slot_field], tp=tp, slot_key=str(slot_key),
                                lv=int(slot.get("lv", 0) or 0),
                                reset_count=int(slot.get("resetCount", 0) or 0),
                                options=options))
    return out
