"""Per-tick service: publish pending decisions + execute human commands."""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict
from pathlib import Path

from nta_agent.execution.armies import army_view
from nta_agent.execution.decisions import pending_decisions
from nta_agent.execution.equipment import pawn_equipment
from nta_agent.runtime.commands import mark_done, read_pending

_TRACK_TP = {"pawn": 2, "policy": 1, "equip": 3}
_ECODE_RE = re.compile(r"ecode\.(\d+)")


def ecode_reason(config, err: str) -> str:
    """Human-readable meaning of an ecode.NNN inside an error string ('' if none)."""
    m = _ECODE_RE.search(err or "")
    if not m or config is None:
        return ""
    code = int(m.group(1))
    try:
        tbl = config.table("ecode")
    except Exception:
        return ""
    row = tbl.get(code) or tbl.get(str(code)) or {}
    return row.get("vi") or row.get("en") or ""


class DecisionService:
    def __init__(self, actions, config, cfg, on_event=None, armies_every=6, profile=None):
        self.actions = actions
        self.config = config
        self.cfg = cfg
        self._on_event = on_event or (lambda *a: None)
        self.armies_every = armies_every
        self._armies_counter = 0
        self.profile = profile  # shared live Profile for profile_edit commands

    def _write_decisions(self, state) -> None:
        data = [asdict(d) for d in pending_decisions(state, self.config)]
        path = Path(self.cfg.decisions_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)

    def _write_equipment(self, state) -> None:
        data = pawn_equipment(state, self.config)
        path = Path(self.cfg.equipment_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)

    def _write_armies(self) -> None:
        data = army_view(self.actions.get_player_armys(), self.config)
        path = Path(self.cfg.armies_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)

    def _execute(self, cmd: dict) -> None:
        action = cmd.get("action")
        lv = int(cmd.get("lv", 0) or 0)
        if action == "profile_edit":
            if self.profile is not None:
                from nta_agent.execution.profile import apply_edits
                apply_edits(self.profile, cmd.get("edits") or {})
            return
        if action == "equip":
            pawn_id = int(cmd["pawn_id"])
            equip_uid = cmd["equip_uid"]
            skin_id = int(cmd.get("skin_id", 0) or 0)
            atk = int(cmd.get("attack_speed", 0) or 0)
            # 1) config = default for pawns drilled later
            self.actions.change_pawn_equip(pawn_id, equip_uid, skin_id, atk)
            # 2) also equip pawns already on the field — the config alone doesn't
            # touch them. sync_equip=1 applies to EVERY pawn of this type across
            # non-marching armies, so one call on any such pawn suffices.
            for a in self.actions.get_player_armys():
                if int(a.get("state", 0) or 0) == 1:  # marching: can't change attr
                    continue
                p = next((q for q in (a.get("pawns") or [])
                          if int(q.get("id", 0) or 0) == pawn_id), None)
                if p:
                    self.actions.change_pawn_attr(
                        int(a.get("index", 0) or 0), str(a.get("uid")), str(p.get("uid")),
                        equip_uid, sync_equip=1, skin_id=skin_id, attack_speed=atk)
                    break
            return
        track = cmd.get("track")
        tp = _TRACK_TP.get(track)
        if tp is None:
            raise ValueError(f"unknown track {track!r}")
        if action == "select":
            self.actions.study_select(lv, int(cmd["ceri_id"]), tp)
        elif action == "reroll":
            self.actions.ceri_reset(lv, tp)
        else:
            raise ValueError(f"unknown action {action!r}")

    def tick(self, state) -> None:
        try:
            self._write_decisions(state)
        except Exception as e:  # observability must not kill the loop
            sys.stderr.write(f"[decisions] write failed: {e}\n")
        try:
            self._write_equipment(state)
        except Exception as e:
            sys.stderr.write(f"[equipment] write failed: {e}\n")
        if self._armies_counter <= 0:
            self._armies_counter = self.armies_every - 1
            try:
                self._write_armies()  # network call — never kill the loop
            except Exception as e:
                sys.stderr.write(f"[armies] fetch failed: {e}\n")
        else:
            self._armies_counter -= 1
        for cmd in read_pending(self.cfg.commands_path, self.cfg.commands_done_path):
            try:
                self._execute(cmd)
                self._on_event("decision_done", {"id": cmd["id"], "action": cmd.get("action")})
            except Exception as e:
                detail = {"id": cmd.get("id"), "action": cmd.get("action"),
                          "track": cmd.get("track"), "lv": cmd.get("lv"),
                          "ceri_id": cmd.get("ceri_id"), "equip_uid": cmd.get("equip_uid"),
                          "pawn_id": cmd.get("pawn_id"),
                          "error": str(e), "reason": ecode_reason(self.config, str(e))}
                detail = {k: v for k, v in detail.items() if v is not None and v != ""}
                self._on_event("decision_error", detail)
                sys.stderr.write(f"[decision] {cmd.get('action')} failed: {e}\n")
            finally:
                mark_done(self.cfg.commands_done_path, cmd["id"])
