"""Build the per-pawn equipment view (human-reserved gear assignment)."""
from __future__ import annotations

import re

# Cocos rich-text markup the game renders as color/format; strip for plain display.
_MARKUP = re.compile(r"</?c(?:olor=[^>]*)?>", re.IGNORECASE)


def _text(config, table_name: str, id_: int) -> str:
    row = config.table(table_name).get(f"name_{id_}") or {}
    return row.get("vi") or row.get("en") or f"#{id_}"


def pawn_name(config, pawn_id: int) -> str:
    return _text(config, "pawnText", pawn_id)


def equip_name(config, equip_id: int) -> str:
    return _text(config, "equipText", equip_id)


def equip_effect(config, equip_id: int) -> str:
    """Human-readable effect/description of an equip (equipText.effect_<id>)."""
    row = config.table("equipText").get(f"effect_{equip_id}") or {}
    return _MARKUP.sub("", row.get("vi") or row.get("en") or "").strip()


def _compatible(config, equip_id: int, pawn_id: int) -> bool:
    row = config.table("equipBase").get(equip_id)
    if not row:
        return True  # unknown -> let the server validate
    ex = str(row.get("exclusive_pawn") or "").strip()
    if not ex:
        return True
    parts = ex.replace("|", ",").split(",")
    return str(pawn_id) in [p.strip() for p in parts]


def _equip_id(e: dict) -> int:
    """Equip type id. Live equips carry only uid (e.g. "6005_1") — derive from it
    when the ``id`` field is absent."""
    if e.get("id"):
        return int(e["id"])
    try:
        return int(str(e.get("uid", "")).split("_")[0])
    except (ValueError, TypeError):
        return 0


def pawn_equipment(state, config) -> list[dict]:
    player = (state.raw or {}).get("player", {}) or {}
    equips = player.get("equips") or []
    by_uid = {e.get("uid"): e for e in equips if isinstance(e, dict)}
    config_map = player.get("configPawnMap") or {}
    # List every UNLOCKED pawn type (pawnSlots entries with a chosen id) plus any
    # that already have an equip config — so the panel shows pawns to gear up even
    # before any config exists (configPawnMap starts empty).
    pawn_ids: set[int] = set()
    for slot in (player.get("pawnSlots") or {}).values():
        if isinstance(slot, dict) and slot.get("id"):
            pawn_ids.add(int(slot["id"]))
    for k in config_map:
        pawn_ids.add(int(k))
    rows: list[dict] = []
    for pid in sorted(pawn_ids):
        cfg = config_map.get(str(pid)) or config_map.get(pid) or {}
        cur_uid = cfg.get("equipUid", "") or ""
        cur = by_uid.get(cur_uid)
        cur_id = _equip_id(cur) if cur else 0
        options = [
            {"uid": e["uid"], "id": _equip_id(e), "name": equip_name(config, _equip_id(e)),
             "desc": equip_effect(config, _equip_id(e))}
            for e in equips
            if isinstance(e, dict) and _compatible(config, _equip_id(e), pid)
        ]
        rows.append({
            "pawn_id": pid,
            "pawn_name": pawn_name(config, pid),
            "current_equip_uid": cur_uid,
            "current_equip_name": equip_name(config, cur_id) if cur else "",
            "current_equip_desc": equip_effect(config, cur_id) if cur else "",
            "skin_id": int(cfg.get("skinId", 0) or 0),
            "attack_speed": int(cfg.get("attackSpeed", 0) or 0),
            "options": options,
        })
    return rows
