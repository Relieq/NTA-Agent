"""Build a read-only per-army / per-troop view for the dashboard."""
from __future__ import annotations

STATE_LABELS = {0: "rảnh", 1: "hành quân", 2: "đang đánh"}


def _name(config, table_name: str, id_: int) -> str:
    row = config.table(table_name).get(f"name_{id_}") or {}
    return row.get("vi") or row.get("en") or f"#{id_}"


def army_view(armys: list[dict], config) -> list[dict]:
    rows: list[dict] = []
    for a in armys or []:
        if not isinstance(a, dict):
            continue
        pawns = []
        for p in a.get("pawns") or []:
            equip = p.get("equip") or {}
            eid = equip.get("id") if isinstance(equip, dict) else None
            if not eid and isinstance(equip, dict):  # live EquipInfo: uid "<id>_<lv>" only
                head = str(equip.get("uid") or "").split("_")[0]
                eid = int(head) if head.isdigit() else None
            pawns.append({
                "uid": p.get("uid", ""),
                "id": int(p.get("id", 0) or 0),
                "name": _name(config, "pawnText", int(p.get("id", 0) or 0)),
                "lv": int(p.get("lv", 0) or 0),
                "attack_speed": int(p.get("attackSpeed", 0) or 0),
                "equip_name": _name(config, "equipText", eid) if eid else "",
                # heroes can't be dismissed: keep the flag (only when set, so rows stay small)
                **({"hero": True} if p.get("hero") or p.get("avatarArmyUID") else {}),
            })
        state = int(a.get("state", 0) or 0)
        rows.append({
            "uid": a.get("uid", ""),
            "name": a.get("name", "") or "",
            "index": int(a.get("index", 0) or 0),
            "state": state,
            "state_label": STATE_LABELS.get(state, str(state)),
            "march_speed": int(a.get("marchSpeed", 0) or 0),
            "pawns": pawns,
        })
    return rows
