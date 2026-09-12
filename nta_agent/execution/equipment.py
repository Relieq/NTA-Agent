"""Build the per-pawn equipment view (human-reserved gear assignment)."""
from __future__ import annotations


def _text(config, table_name: str, id_: int) -> str:
    row = config.table(table_name).get(f"name_{id_}") or {}
    return row.get("vi") or row.get("en") or f"#{id_}"


def pawn_name(config, pawn_id: int) -> str:
    return _text(config, "pawnText", pawn_id)


def equip_name(config, equip_id: int) -> str:
    return _text(config, "equipText", equip_id)


def _compatible(config, equip_id: int, pawn_id: int) -> bool:
    row = config.table("equipBase").get(equip_id)
    if not row:
        return True  # unknown -> let the server validate
    ex = str(row.get("exclusive_pawn") or "").strip()
    if not ex:
        return True
    parts = ex.replace("|", ",").split(",")
    return str(pawn_id) in [p.strip() for p in parts]


def pawn_equipment(state, config) -> list[dict]:
    player = (state.raw or {}).get("player", {}) or {}
    equips = player.get("equips") or []
    by_uid = {e.get("uid"): e for e in equips if isinstance(e, dict)}
    rows: list[dict] = []
    for pid_str, cfg in (player.get("configPawnMap") or {}).items():
        if not isinstance(cfg, dict):
            continue
        pid = int(pid_str)
        cur_uid = cfg.get("equipUid", "") or ""
        cur = by_uid.get(cur_uid)
        cur_name = equip_name(config, cur["id"]) if cur else ""
        options = [
            {"uid": e["uid"], "id": e["id"], "name": equip_name(config, e["id"])}
            for e in equips
            if isinstance(e, dict) and _compatible(config, e.get("id", 0), pid)
        ]
        rows.append({
            "pawn_id": pid,
            "pawn_name": pawn_name(config, pid),
            "current_equip_uid": cur_uid,
            "current_equip_name": cur_name,
            "skin_id": int(cfg.get("skinId", 0) or 0),
            "attack_speed": int(cfg.get("attackSpeed", 0) or 0),
            "options": options,
        })
    return rows
