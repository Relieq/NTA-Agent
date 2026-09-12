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


def _desc(config, text_name: str, value: int) -> str:
    if text_name == "policyText":
        key = f"desc_{value}"
    elif text_name == "equipText":
        key = f"effect_{value}"
    else:
        return ""
    row = config.table(text_name).get(key) or {}
    return row.get("vi") or row.get("en") or ""


def pending_decisions(state, config) -> list[Decision]:
    player = (state.raw or {}).get("player", {}) or {}
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
            # selectIds ARE the offered ids directly (pawn/policy/equip id), not
            # ceri-row ids — resolve name/desc straight from them.
            options = [
                {"ceri_id": sid, "value": sid,
                 "name": _name(text_table, sid),
                 "desc": _desc(config, text_name, sid)}
                for sid in select_ids
            ]
            out.append(Decision(track=_TRACK_NAME[slot_field], tp=tp, slot_key=str(slot_key),
                                lv=int(slot.get("lv", 0) or 0),
                                reset_count=int(slot.get("resetCount", 0) or 0),
                                options=options))
    return out
