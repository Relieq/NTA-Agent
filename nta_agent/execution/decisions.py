"""Detect reserved ceri decisions (unlock pawn/policy/equip) pending a human pick."""
from __future__ import annotations

import re
from dataclasses import dataclass

# Cocos rich-text markup the game renders as color/format; strip for plain display.
_MARKUP = re.compile(r"</?c(?:olor=[^>]*)?>", re.IGNORECASE)


def _clean(text: str) -> str:
    return _MARKUP.sub("", text or "").strip()

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
        row = config.table(text_name).get(f"desc_{value}") or {}
        tmpl = _clean(row.get("vi") or row.get("en") or "")
        if not tmpl:
            return ""
        # The game fills {0} with the policy's base value (value.split(",")[0]) —
        # see engine: policyText.desc_<id> setLocaleKey(..., r.value.split(",")[0]).
        pol = config.table("policy").get(value) or {}
        arg = str(pol.get("value", "")).split(",")[0]
        return tmpl.replace("{0}", arg) if arg else tmpl
    if text_name == "equipText":
        # equip stat ranges + its EFFECT. equipBase.effect is an effect ID; its text
        # is equipText.effect_<EFFECT_ID> (NOT effect_<equipId>), with {0}=value,
        # {1}=odds filled from equipEffect[effectId] (value/odds are min,max ranges
        # because forging rolls within them).
        base = config.table("equipBase").get(value) or {}
        parts: list[str] = []
        atk = str(base.get("attack") or "").strip()
        hp = str(base.get("hp") or "").strip()
        if atk:
            parts.append(f"ST {atk.replace(',', '–')}")
        if hp:
            parts.append(f"Máu {hp.replace(',', '–')}")
        # ``effect`` is one effect id or a "|"-joined list of them (high-tier
        # equips carry several); render each. A raw int() on the whole string
        # threw ValueError and failed the decisions write every tick.
        for tok in str(base.get("effect", "") or "").split("|"):
            tok = tok.strip()
            if not tok or not tok.lstrip("-").isdigit():
                continue
            eff_id = int(tok)
            if not eff_id:
                continue
            row = config.table(text_name).get(f"effect_{eff_id}") or {}
            tmpl = _clean(row.get("vi") or row.get("en") or "")
            if not tmpl:
                continue
            fx = config.table("equipEffect").get(eff_id) or {}
            sfx = str(fx.get("suffix") or "")
            val = str(fx.get("value") or "").strip()
            odds = str(fx.get("odds") or "").strip()
            tmpl = tmpl.replace("{0}", (val.replace(",", "–") + sfx) if val else "")
            tmpl = tmpl.replace("{1}", (odds.replace(",", "–") + "%") if odds else "")
            parts.append(tmpl)
        if str(base.get("exclusive_pawn") or "").strip():
            parts.append("(chuyên dụng)")  # pawn-locked; agent won't auto-forge
        return " · ".join(parts)
    return ""


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
