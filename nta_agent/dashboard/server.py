"""Thin stdlib HTTP layer serving the dashboard page + read-only JSON APIs."""
from __future__ import annotations

import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from nta_agent.dashboard.data import read_json_array, read_state, tail_events
from nta_agent.dashboard.names import build_label, load_build_names
from nta_agent.dashboard.page import INDEX_HTML
from nta_agent.runtime.commands import append_command
from nta_agent.runtime.config import RuntimeConfig

_VALID_TRACK = {"pawn", "policy", "equip"}
_RES_KEYS = ("cereal", "timber", "stone", "iron", "gold", "stamina",
             "exp_book", "up_scroll", "fixator")

_STATIC_DIR = (Path(__file__).parent / "static").resolve()
_STATIC_TYPES = {".js": "text/javascript", ".mjs": "text/javascript",
                 ".css": "text/css", ".map": "application/json"}


def serve_static(relpath: str):
    """Return (status, content_type, body_bytes) for a file under the static dir.

    Guards against path traversal and non-whitelisted extensions. 404 on any miss.
    """
    ext = ("." + relpath.rsplit(".", 1)[-1]).lower() if "." in relpath else ""
    ctype = _STATIC_TYPES.get(ext)
    if not ctype:
        return 404, "text/plain", b"not found"
    try:
        target = (_STATIC_DIR / relpath).resolve()
        target.relative_to(_STATIC_DIR)  # raises if traversal escaped the dir
        body = target.read_bytes()
    except (ValueError, OSError):
        return 404, "text/plain", b"not found"
    return 200, ctype + "; charset=utf-8", body


def _chat_state():
    """Minimal state object the digest can read (chat needs no live resources)."""
    return SimpleNamespace(main_city_index=0,
                           resources=SimpleNamespace(**{k: 0 for k in _RES_KEYS}), raw={})


def _pawn_names(cfg) -> dict:
    """{pawn_id_str: Vietnamese name} from pawnText — so the LLM sees readable troop
    types instead of raw ids (better input => it picks the right army)."""
    try:
        from nta_agent.data.config import GameConfig
        rows = GameConfig.load().table("pawnText")
    except Exception:
        return {}
    out = {}
    for key, row in rows.items():
        s = str(key)
        if s.startswith("name_") and isinstance(row, dict):
            out[s[len("name_"):]] = row.get("vi") or row.get("en") or s
    return out


def _troops_label(comp: dict, names: dict) -> str:
    """'6× Lính Trường Thương, 3× Lính Cung Kỵ' from a composition dict."""
    parts = sorted(comp.items(), key=lambda kv: -kv[1])
    return ", ".join(f"{n}× {names.get(str(pid), pid)}" for pid, n in parts)


def _armies_from_disk(cfg) -> list:
    try:
        return json.loads(Path(cfg.armies_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _dominant_by_uid(armies) -> dict:
    from collections import Counter
    out = {}
    for a in armies:
        comp = Counter(str(p.get("id")) for p in (a.get("pawns") or []))
        if comp:
            out[str(a.get("uid"))] = max(comp, key=comp.get)
    return out


def _unlocked_pawn_ids(cfg):
    """Pawn types unlocked right now (snapshot player.pawn_slots), or None if unknown.
    Unlocks reset when the main city is re-created — never assume a type."""
    try:
        snap = json.loads(Path(cfg.snapshot_path).read_text(encoding="utf-8"))
        ids = (snap.get("player") or {}).get("pawn_slots")
    except (OSError, ValueError, AttributeError):
        return None
    return {int(i) for i in ids} if isinstance(ids, list) and ids else None


_EDIT_LABELS = {
    "occupy.expansion": "Kiểu mở rộng đất",
    "occupy.max_march_ms": "Thời gian hành quân tối đa (ms)",
    "occupy.policy.order": "Đội dẫn đầu khi đánh",
    "occupy.loot.enabled": "Ưu tiên nhặt rương",
    "occupy.loot.min_reward_per_chest": "Giá trị rương tối thiểu",
    "revive.enabled": "Tự hồi sinh lính",
    "logistics.enabled": "Tự bổ sung quân",
    "logistics.target": "Số lính mục tiêu mỗi đội",
    "army.active": "Đội hình đang dùng",
}


def describe_edits(clean: dict) -> list[str]:
    """Readable Vietnamese lines for applied profile edits (the chat used to print
    raw JSON)."""
    out: list[str] = []

    def fmt(v):
        if isinstance(v, bool):
            return "bật" if v else "tắt"
        return json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)

    def walk(d, path):
        for k, v in d.items():
            p = f"{path}.{k}" if path else str(k)
            if p == "notes" and isinstance(v, list):
                out.append(f"Ghi chú chiến lược: {len(v)} mục")
            elif p == "army.strike_target" and v == []:
                out.append("Huỷ mục tiêu gom quân")
            elif p == "army.presets" and isinstance(v, dict):
                out.append("Đội hình đã lưu: " + ", ".join(v) if v else "Xoá đội hình đã lưu")
            elif isinstance(v, dict) and v and p not in _EDIT_LABELS:
                walk(v, p)
            elif p not in ("rationale", "advice", "lessons", "question", "army_renames"):
                out.append(f"{_EDIT_LABELS.get(p, p)} → {fmt(v)}")

    walk(clean or {}, "")
    return out


def strike_summary(targets: list[dict]) -> str:
    """'4 đội × 9 Lính Cường Nỏ (Đội 2–Đội 5) + 1 đội × 9 Lính Khiên Lớn (Đội 1)'."""
    parts = []
    for t in targets:
        s = f"{t['armies']} đội × {t['size']} {t.get('name') or t['pawn_id']}"
        if t.get("names"):
            s += " (" + ", ".join(t["names"]) + ")"
        parts.append(s)
    return " + ".join(parts)


def confirm_strike(cfg, strike) -> dict:
    """Apply a strike-group goal the player CONFIRMED: re-check unlocks, save it and
    hand it to the running agent (profile_edit). Pure of HTTP."""
    from nta_agent.brain.guard import sanitize_strike
    from nta_agent.execution.profile import apply_edits, load_profile, save_profile
    names = {int(k): v for k, v in _pawn_names(cfg).items() if str(k).isdigit()}
    clean, notes = sanitize_strike(strike, _unlocked_pawn_ids(cfg), "", names,
                                   trust_size=True)
    if not clean:
        return {"ok": False, "error": "Không còn mục tiêu hợp lệ. " + " ".join(notes)}
    edits = {"army": {"strike_target": clean}}
    profile = load_profile(cfg.profile_path)
    apply_edits(profile, edits)
    save_profile(profile, cfg.profile_path)
    append_command(cfg.commands_path, {"action": "profile_edit", "edits": edits})
    return {"ok": True, "strike_target": clean, "summary": strike_summary(clean),
            "notes": notes}


def chat_reply_summary(out: dict) -> str:
    """What the brain answered, in one line, for the next turn's chat history."""
    if not out.get("ok"):
        return "(lỗi: " + str(out.get("error", "")) + ")"
    parts = []
    if out.get("strike"):
        parts.append("Đề xuất tạo nhóm (chờ xác nhận): " + out["strike"]["summary"])
    if out.get("renames"):
        parts.append("Đề xuất đổi tên: " + ", ".join(
            f"{r.get('current_name') or r['uid']}→{r['name']}" for r in out["renames"]))
    if out.get("question"):
        parts.append("Hỏi lại: " + out["question"])
    if out.get("applied_text"):
        parts.append("Đã áp dụng: " + "; ".join(out["applied_text"]))
    parts += list(out.get("notices") or [])
    return " | ".join(parts) or (out.get("rationale") or "(không thay đổi)")


# Player nicknames for pawn types (names, not unlock assumptions — the type must still
# be in unlocked_pawns to be used).
_PAWN_ALIASES = {3305: ["IMP"]}


def handle_chat(cfg, message, *, history=None, propose=None):
    """LLM chat turn: apply profile edits immediately, and PROPOSE (not execute) any
    army renames the player asked for — renames need explicit confirmation first
    (see confirm_renames). Pure of HTTP."""
    from collections import Counter

    from nta_agent.brain import llm as _llm
    from nta_agent.brain.digest import digest
    from nta_agent.brain.guard import rename_ambiguity, sanitize_edits, sanitize_renames
    from nta_agent.brain.llm import BrainUnavailable
    from nta_agent.execution.profile import apply_edits, load_profile, save_profile
    propose = propose or _llm.propose
    profile = load_profile(cfg.profile_path)
    armies = _armies_from_disk(cfg)
    valid = {str(a.get("uid")) for a in armies}
    try:
        from nta_agent.data.config import GameConfig
        valid_build = set(GameConfig.load().in_city_build_ids())
    except Exception:
        valid_build = None
    names = _pawn_names(cfg)
    dg = digest(_chat_state(), profile, armies)
    # Better INPUT: label each army's troops by pawn NAME so the LLM can match a
    # description ("đội rìu khiên") to the right uid without knowing pawn ids.
    for row in dg.get("armies", []):
        row["troops"] = _troops_label(row.get("composition") or {}, names)
    # The pawn types the player can field NOW (unlocks reset on a re-created city):
    # the LLM must pick strike_target ids from this list, never from memory.
    unlocked = _unlocked_pawn_ids(cfg)
    pawn_names = {int(k): v for k, v in names.items() if str(k).isdigit()}
    if unlocked is not None:
        dg["unlocked_pawns"] = [{"id": i, "name": pawn_names.get(i, str(i)),
                                 **({"aliases": _PAWN_ALIASES[i]} if i in _PAWN_ALIASES else {})}
                                for i in sorted(unlocked)]
    try:
        edits = propose(dg, profile, instruction=message, history=history or [])
    except BrainUnavailable as e:
        return {"ok": False, "error": "brain unavailable: %s" % e}
    except Exception as e:  # network/parse — surface, change nothing
        return {"ok": False, "error": str(e)}
    # A strike-group goal can rally/recruit/dismiss troops: it is PROPOSED for
    # confirmation (like renames), never applied straight from chat. [] (clear) is safe.
    raw_strike = None
    if isinstance(edits, dict) and "army.strike_target" in edits:
        # LLMs sometimes flatten the path ({"army.strike_target": [...]}): accept it
        edits.setdefault("army", {})
        if isinstance(edits["army"], dict):
            edits["army"].setdefault("strike_target", edits.pop("army.strike_target"))
    army_in = edits.get("army") if isinstance(edits, dict) else None
    if isinstance(army_in, dict) and army_in.get("strike_target"):
        raw_strike = army_in.pop("strike_target")
    clean = sanitize_edits(edits, profile, valid, valid_build_ids=valid_build)
    if clean:
        apply_edits(profile, clean)
        save_profile(profile, cfg.profile_path)
        append_command(cfg.commands_path, {"action": "profile_edit", "edits": clean})
    # Renames: the LLM PICKS the armies (by uid); we validate but DO NOT execute —
    # the player confirms first (confirm_renames queues the commands).
    dominant = _dominant_by_uid(armies)
    renames = sanitize_renames(edits, valid, dominant)
    by_uid = {str(a.get("uid")): a for a in armies}
    question = str((edits or {}).get("question", "")).strip()
    # Deterministic guard after the LLM: a positional or shared-pawn-type reference
    # to an army the player didn't NAME is ambiguous -> ask instead of proposing.
    info = []
    for a in armies:
        comp = Counter(str(p.get("id")) for p in (a.get("pawns") or []))
        total = sum(comp.values())
        info.append({"uid": str(a.get("uid")), "name": a.get("name", ""),
                     "dominant": dominant.get(str(a.get("uid"))),
                     "share": (max(comp.values()) / total) if total else 1.0,
                     "troops": _troops_label(dict(comp), names)})
    from nta_agent.brain.guard import sanitize_strike
    strike, notices = ([], [])
    if raw_strike:
        strike, notices = sanitize_strike(raw_strike, unlocked, message, pawn_names)
    if strike:
        # Names the player gave belong to the NEW group (renamed once it's assembled),
        # not to whichever existing armies the LLM guessed.
        renames, question = [], ""
    else:
        guard_q = rename_ambiguity(message, renames, info,
                                   aliases=[a for v in _PAWN_ALIASES.values() for a in v])
        if guard_q:
            renames, question = [], guard_q
    proposal = []
    for r in renames:
        a = by_uid.get(r["uid"], {})
        comp = Counter(str(p.get("id")) for p in (a.get("pawns") or []))
        proposal.append({"uid": r["uid"], "name": r["name"],
                         "current_name": a.get("name", ""),
                         "troops": _troops_label(dict(comp), names)})
    return {"ok": True, "applied": clean, "rationale": (edits or {}).get("rationale", ""),
            "applied_text": describe_edits(clean),
            "strike": ({"targets": strike, "summary": strike_summary(strike)}
                       if strike else None),
            "notices": notices,
            "renames": proposal, "needs_confirm": bool(proposal) or bool(strike),
            "question": question,
            "active": profile.army.get("active", ""),
            "presets": list(profile.army.get("presets") or {}),
            "notes": profile.notes}


def confirm_renames(cfg, renames):
    """Execute confirmed renames: re-validate against the CURRENT armies, then queue
    the rename_army commands for the hands. Pure of HTTP."""
    from nta_agent.brain.guard import sanitize_renames
    armies = _armies_from_disk(cfg)
    valid = {str(a.get("uid")) for a in armies}
    clean = sanitize_renames({"army_renames": renames}, valid, _dominant_by_uid(armies))
    idx_by_uid = {str(a.get("uid")): int(a.get("index", 0) or 0) for a in armies}
    for r in clean:
        append_command(cfg.commands_path, {"action": "rename_army",
                                           "index": idx_by_uid.get(r["uid"], 0),
                                           "uid": r["uid"], "name": r["name"]})
    return {"ok": True, "queued": clean}


def _valid_build_ids():
    try:
        from nta_agent.data.config import GameConfig
        return set(GameConfig.load().in_city_build_ids())
    except Exception:
        return None


def read_profile_view(cfg) -> dict:
    """Current profile plus building-name map + in-city catalogue (for the editor),
    filtered to the current game mode (room_type from the snapshot)."""
    from nta_agent.dashboard.names import load_build_names
    from nta_agent.execution.profile import active_formation, load_profile
    profile = load_profile(cfg.profile_path)
    names = load_build_names()
    room_type = read_state(cfg.snapshot_path).get("room_type")
    try:
        from nta_agent.data.config import GameConfig
        ids = GameConfig.load().in_city_build_ids(room_type)
    except Exception:
        ids = sorted(_valid_build_ids() or set())
    catalogue = [{"id": bid, "name": names.get(bid, f"#{bid}")} for bid in ids]
    return {"active": profile.army.get("active", ""),
            "presets": list(profile.army.get("presets") or {}),
            # effective farm group (active preset's, else flat) so FarmGroupPanel
            # can restore the saved selection after a reload.
            "army": {"group": active_formation(profile).get("group") or []},
            "notes": profile.notes,
            "build": profile.build,
            "leveling": getattr(profile, "leveling", {}),
            "names": {str(k): v for k, v in names.items()},
            "catalogue": catalogue}


def read_territory_view(cfg) -> dict:
    """Own territory (main city, forts with pos + auto-support, garrisons) from the snapshot."""
    st = read_state(cfg.snapshot_path)
    mw = int(st.get("map_width") or 600)
    forts = [{"index": f["index"], "auto_support": f.get("auto_support", False),
              "x": f["index"] % mw, "y": f["index"] // mw}
             for f in (st.get("forts") or [])]
    return {"main_city": st.get("main_city_index", 0), "forts": forts,
            "garrisons": st.get("garrisons") or [], "map_width": mw}


def read_forts_view(cfg) -> dict:
    """Fort recommendations (owned count + recs) from forts.json, if present."""
    try:
        data = json.loads(Path(cfg.forts_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"owned_count": 0, "owned_cells": [], "accepted": [], "rejected": [],
                "enemy_cells": [], "enemy_cities": [], "frontier": [], "recommendations": [],
                "fort_zone": [], "fort_count": 0, "forts": [], "fort_cap": 0,
                "threats": [], "threat_summary": {"count": 0}, "pending": []}
    return {"owned_count": data.get("owned_count", 0),
            "owned_cells": data.get("owned_cells") or [],
            "accepted": data.get("accepted") or [],
            "rejected": data.get("rejected") or [],
            "enemy_cells": data.get("enemy_cells") or [],
            "enemy_cities": data.get("enemy_cities") or [],
            "frontier": data.get("frontier") or [],
            "recommendations": data.get("recommendations") or [],
            "fort_zone": data.get("fort_zone") or [],
            "fort_count": data.get("fort_count", 0),
            "forts": data.get("forts") or [],
            "fort_cap": data.get("fort_cap", 0),
            "threats": data.get("threats") or [],
            "threat_summary": data.get("threat_summary") or {"count": 0},
            "pending": _read_pending_forts(cfg)}


def read_dig(cfg) -> dict:
    """The dig status (dig.json, written by the agent's DigService) + whether a
    dashboard request is still waiting for the agent to pick it up."""
    try:
        d = json.loads(Path(cfg.dig_state_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    if not isinstance(d, dict):
        d = {}
    try:
        req = json.loads(Path(cfg.dig_request_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        req = {}
    pending = bool(req.get("seq") is not None and req.get("seq") != d.get("seq"))
    out = {"state": "idle", **d, "pending": pending}
    if pending:
        out["pending_op"] = req.get("op")
        if req.get("op") == "cancel":  # show it at once: the agent stops digging on read
            out["state"] = "cancelled"
            out["cancel_pending"] = True
    return out


def dig_command(cfg, op: str, body: dict) -> dict:
    """request {index, buffer} | confirm | replan | cancel -> dig_request.json (a fresh seq),
    which the agent's DigService answers in dig.json."""
    import time as _time
    if op not in ("request", "confirm", "cancel", "replan"):
        return {"ok": False, "error": "thao tác không hợp lệ"}
    req = {"seq": _time.time_ns(), "op": op}
    if op == "request":
        try:
            idx = int(body["index"])
        except (KeyError, TypeError, ValueError):
            return {"ok": False, "error": "cần chọn ô đích"}
        if not 0 <= idx < 600 * 600:
            return {"ok": False, "error": "ô ngoài bản đồ"}
        try:
            buffer = int(body.get("buffer", 2))
        except (TypeError, ValueError):
            buffer = 2
        req.update(index=idx, buffer=max(0, min(6, buffer)))
    p = Path(cfg.dig_request_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(req), encoding="utf-8")
    os.replace(tmp, p)
    return {"ok": True, **read_dig(cfg)}


def _read_pending_forts(cfg) -> list:
    """Fort cells queued to build (waiting on resources), as [{index, x, y}]."""
    from nta_agent.runtime import fort_queue
    out = []
    for idx in fort_queue.load(cfg.pending_forts_path):
        out.append({"index": idx, "x": idx % 600, "y": idx // 600})
    return out


def read_failures(cfg) -> dict:
    """Recent failure-ledger events (failures.json) for the learning panel."""
    try:
        rows = json.loads(Path(cfg.failures_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rows = []
    return {"failures": list(reversed(rows))[:30] if isinstance(rows, list) else []}


def read_lessons(cfg) -> dict:
    """Distilled lessons (lessons.json) for the learning panel."""
    try:
        rows = json.loads(Path(cfg.lessons_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rows = []
    return {"lessons": rows if isinstance(rows, list) else []}


def read_health(cfg) -> dict:
    """Connection-health telemetry (health.json) for the status header (F1)."""
    try:
        return json.loads(Path(cfg.health_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"connected": False, "last_activity_age": 0, "recover_count": 0,
                "degraded": False}


def read_settings() -> dict:
    from nta_agent import settings
    return settings.view()


def update_settings(body: dict) -> dict:
    from nta_agent import settings
    if not isinstance(body, dict) or not body:
        return {"ok": False, "error": "không có gì để lưu"}
    try:
        settings.set_values(body)
    except KeyError as e:
        return {"ok": False, "error": f"khoá không hợp lệ: {e.args[0]}"}
    return {"ok": True, "settings": settings.view()}


def test_openai_key(opener=None) -> dict:
    """Probe the stored key with GET /v1/models (free). Never echoes the key."""
    import urllib.error
    import urllib.request

    from nta_agent import settings
    key = settings.get("openai_api_key")
    if not key:
        return {"ok": False, "error": "chưa nhập OpenAI API key"}
    req = urllib.request.Request("https://api.openai.com/v1/models",
                                 headers={"Authorization": "Bearer " + key})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=8) as r:
            return {"ok": 200 <= r.status < 300}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": "key bị từ chối (401)" if e.code == 401 else f"HTTP {e.code}"}
    except (urllib.error.URLError, OSError) as e:
        return {"ok": False, "error": f"không kết nối được: {e}"}


_CHAT_PREFIXES = ("gpt-", "chatgpt-", "o1", "o3", "o4")
_NOT_CHAT = ("audio", "realtime", "tts", "transcribe", "image", "search", "embedding",
             "instruct", "moderation", "whisper", "dall-e",
             "codex", "-pro", "gpt-live")  # Responses-API-only / non-chat families
_SNAPSHOT = re.compile(r"-\d{4}-\d{2}-\d{2}$|-\d{4}$")


def list_openai_models(opener=None) -> dict:
    """Chat-capable models the stored key can use (GET /v1/models), for the Settings
    dropdown. Dated snapshots and non-chat families are hidden to keep it short."""
    import urllib.error
    import urllib.request

    from nta_agent import settings
    key = settings.get("openai_api_key")
    if not key:
        return {"ok": False, "models": [], "error": "chưa nhập OpenAI API key"}
    req = urllib.request.Request("https://api.openai.com/v1/models",
                                 headers={"Authorization": "Bearer " + key})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"ok": False, "models": [],
                "error": "key bị từ chối (401)" if e.code == 401 else f"HTTP {e.code}"}
    except (urllib.error.URLError, OSError, ValueError) as e:
        return {"ok": False, "models": [], "error": f"không lấy được danh sách: {e}"}
    ids = sorted({m.get("id", "") for m in data.get("data", []) if isinstance(m, dict)})
    models = [i for i in ids if i.startswith(_CHAT_PREFIXES)
              and not any(x in i for x in _NOT_CHAT) and not _SNAPSHOT.search(i)]
    return {"ok": True, "models": models}


def read_app_info() -> dict:
    from nta_agent import paths
    return {"version": paths.app_version(), "packaged": paths.is_packaged(),
            "data_dir": str(paths.data_dir())}


def read_forge_view(cfg) -> dict:
    """Recast panel: agent-written forge.json rows, with targets re-read FRESH from
    forge_targets.json so an edit shows immediately (not on the next agent tick)."""
    from nta_agent.runtime import forge_targets
    try:
        data = json.loads(Path(cfg.forge_view_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    targets = forge_targets.load(cfg.forge_targets_path)
    equips = [{**e, "target": targets.get(str(e.get("uid")))}
              for e in (data.get("equips") or []) if isinstance(e, dict)]
    return {"equips": equips, "busy": data.get("busy"), "iron": data.get("iron", 0)}


def set_forge_target(cfg, body: dict) -> dict:
    """Set/remove one equip's recast target. Either per-stat minimums
    ``{uid, budget, mins: {"<effectType>.value"|"<effectType>.odds": min}}`` (blank =
    don't care), or the legacy ``{uid, budget, threshold_pct}``; ``{uid, remove}``."""
    import re as _re

    from nta_agent.runtime import forge_targets
    uid = str((body or {}).get("uid") or "").strip()
    if not uid:
        return {"ok": False, "error": "thiếu uid"}
    if body.get("remove"):
        forge_targets.remove(cfg.forge_targets_path, uid)
        return {"ok": True}
    try:
        budget = int(body.get("budget"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "ngân sách không hợp lệ"}
    if budget < 0:
        return {"ok": False, "error": "ngân sách ≥ 0"}
    if "mins" in body:
        # The rollable range of each effect number (from the agent's forge view): a
        # minimum above the best roll can never be met — the agent would burn the whole
        # iron budget — and one below the worst roll means nothing. Unknown -> unchecked.
        equip = next((e for e in read_forge_view(cfg)["equips"]
                      if str(e.get("uid")) == uid), None)
        bounds = {}
        for p in (equip or {}).get("possible") or []:
            for part in ("value", "odds"):
                bounds[f"{p.get('type')}.{part}"] = (list(p.get(f"{part}_range") or []),
                                                     p.get("label") or "")
        mins = {}
        for k, v in (body.get("mins") or {}).items():
            if v in ("", None):
                continue  # blank = don't care about this stat
            if not _re.fullmatch(r"\d+\.(value|odds)", str(k)):
                return {"ok": False, "error": f"chỉ số không hợp lệ: {k}"}
            try:
                fv = float(v)
            except (TypeError, ValueError):
                return {"ok": False, "error": f"mức tối thiểu không hợp lệ: {k}"}
            if fv < 0:
                return {"ok": False, "error": "mức tối thiểu ≥ 0"}
            if str(k) in bounds:
                rng, label = bounds[str(k)]
                what = ("tỉ lệ" if str(k).endswith(".odds") else "giá trị") + f" của «{label}»"
                if len(rng) < 2:
                    return {"ok": False, "error": f"{what} không có số để đặt mức"}
                lo, hi = float(rng[0]), float(rng[1])
                if not lo <= fv <= hi:
                    return {"ok": False,
                            "error": f"{what} chỉ roll được {rng[0]}–{rng[1]}; "
                                     f"mức {v} nằm ngoài khoảng"}
            mins[str(k)] = fv
        if not mins:
            return {"ok": False, "error": "đặt ít nhất một mức tối thiểu"}
        forge_targets.set_target(cfg.forge_targets_path, uid, 1.0, budget, mins=mins)
        return {"ok": True}
    try:
        pct = float(body.get("threshold_pct"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "ngưỡng không hợp lệ"}
    if not 0 <= pct <= 100:
        return {"ok": False, "error": "ngưỡng 0–100%"}
    forge_targets.set_target(cfg.forge_targets_path, uid, pct / 100.0, budget)
    return {"ok": True}


def read_alerts(cfg) -> dict:
    """Early-warning state (alerts.json): capture / incoming enemy marches / approach."""
    try:
        return json.loads(Path(cfg.alerts_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"level": "ok", "captured": None, "incoming": [], "approach": {}}


def read_errors(cfg) -> dict:
    """Structured error summary (errors.jsonl) for a post-run review."""
    from nta_agent.runtime.errorlog import ErrorLog
    try:
        from nta_agent.data.config import GameConfig
        config = GameConfig.load()
    except Exception:
        config = None
    return ErrorLog(cfg.errors_path, config).summary()


def read_intel(cfg) -> dict:
    """Assemble the intel & advisory report (Phase I) from snapshot + forts.json,
    plus the brain's human-facing advice (Phase B)."""
    from nta_agent.execution.intel import build_report
    try:
        advice = json.loads(Path(cfg.brain_advice_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        advice = []
    return build_report(read_state(cfg.snapshot_path), read_forts_view(cfg),
                        brain_advice=advice)


def recompute_forts(cfg) -> dict:
    """Rewrite forts.json from its owned_cells + snapshot + decisions. No game I/O."""
    from nta_agent.data.config import GameConfig
    from nta_agent.execution.fort_advisor import plan_forts
    from nta_agent.runtime import fort_decisions
    try:
        fdj = json.loads(Path(cfg.forts_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        fdj = {}
    cells = fdj.get("owned_cells") or []
    terr = read_territory_view(cfg)
    mw = int(terr.get("map_width") or 600)
    owned = [int(y) * mw + int(x) for x, y in cells]
    main = int(terr.get("main_city") or 0)
    existing = [int(f["index"]) for f in terr.get("forts", [])]
    decisions = fort_decisions.load(cfg.fort_decisions_path)
    try:
        cap = GameConfig.load().max_count(2102)
    except Exception:
        cap = 1
    recs, accepted = plan_forts(main, owned, existing, decisions, cap, map_width=mw)
    payload = {"owned_count": len(owned), "owned_cells": cells,
               "accepted": sorted([i % mw, i // mw] for i in accepted),
               "rejected": sorted([i % mw, i // mw] for i, d in decisions.items()
                                  if d == "rejected"),
               # map layers are re-scanned by FortService, not here — carry them over
               "enemy_cells": fdj.get("enemy_cells") or [],
               "enemy_cities": fdj.get("enemy_cities") or [],
               "frontier": fdj.get("frontier") or [],
               "threats": fdj.get("threats") or [],
               "threat_summary": fdj.get("threat_summary") or {"count": 0},
               "recommendations": recs}
    Path(cfg.forts_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.forts_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
    return payload


def handle_profile_edit(cfg, edits: dict) -> dict:
    """Apply a structured (non-LLM) profile edit: sanitize -> persist -> queue command."""
    from nta_agent.brain.guard import sanitize_edits
    from nta_agent.execution.profile import apply_edits, load_profile, save_profile
    profile = load_profile(cfg.profile_path)
    # army.group is validated against real army uids; without them a group edit
    # (farm-group picker) would be filtered to empty. Read them from armies.json.
    try:
        armies = json.loads(Path(cfg.armies_path).read_text(encoding="utf-8"))
        valid_uids = {str(a.get("uid")) for a in armies if isinstance(a, dict)}
    except (OSError, ValueError):
        valid_uids = set()
    clean = sanitize_edits(edits, profile, valid_uids, valid_build_ids=_valid_build_ids())
    apply_edits(profile, clean)
    save_profile(profile, cfg.profile_path)
    append_command(cfg.commands_path, {"action": "profile_edit", "edits": clean})
    return {"ok": True, "applied": clean, "build": profile.build}


class DashboardServer(ThreadingHTTPServer):
    def __init__(self, addr, handler, cfg: RuntimeConfig):
        super().__init__(addr, handler)
        self.cfg = cfg
        self.build_names = load_build_names()
        self.chat_history = []
        from nta_agent.dashboard.supervisor import AgentSupervisor
        self.supervisor = AgentSupervisor(cfg)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence stderr access logs
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _body(self):
        """Parsed JSON object body, or None (after replying 400) when malformed."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, TypeError):
            body = None
        if not isinstance(body, dict):
            self._json(400, {"ok": False, "error": "bad json"})
            return None
        return body

    def do_GET(self):
        parsed = urlparse(self.path)
        cfg = self.server.cfg
        if parsed.path == "/":
            self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
        elif parsed.path == "/api/state":
            state = read_state(cfg.snapshot_path)
            if state.get("ok"):
                for b in state.get("builds", []):
                    b["name"] = build_label(self.server.build_names, b.get("id", 0))
            self._json(200, state)
        elif parsed.path == "/api/events":
            q = parse_qs(parsed.query)
            try:
                n = int(q.get("n", ["50"])[0])
            except ValueError:
                n = 50
            n = max(1, min(n, 500))
            self._json(200, tail_events(cfg.event_log_path, n))
        elif parsed.path == "/api/decisions":
            self._json(200, read_json_array(cfg.decisions_path))
        elif parsed.path == "/api/equipment":
            self._json(200, read_json_array(cfg.equipment_path))
        elif parsed.path == "/api/armies":
            self._json(200, read_json_array(cfg.armies_path))
        elif parsed.path == "/api/profile":
            self._json(200, read_profile_view(cfg))
        elif parsed.path == "/api/territory":
            self._json(200, read_territory_view(cfg))
        elif parsed.path == "/api/forts":
            self._json(200, read_forts_view(cfg))
        elif parsed.path == "/api/dig":
            self._json(200, read_dig(cfg))
        elif parsed.path == "/api/intel":
            self._json(200, read_intel(cfg))
        elif parsed.path == "/api/errors":
            self._json(200, read_errors(cfg))
        elif parsed.path == "/api/failures":
            self._json(200, read_failures(cfg))
        elif parsed.path == "/api/lessons":
            self._json(200, read_lessons(cfg))
        elif parsed.path == "/api/health":
            self._json(200, read_health(cfg))
        elif parsed.path == "/api/alerts":
            self._json(200, read_alerts(cfg))
        elif parsed.path == "/api/forge":
            self._json(200, read_forge_view(cfg))
        elif parsed.path == "/api/agent/status":
            self._json(200, self.server.supervisor.status())
        elif parsed.path == "/api/setup":
            from nta_agent.setup import steps
            self._json(200, steps.status())
        elif parsed.path == "/api/settings":
            self._json(200, read_settings())
        elif parsed.path == "/api/settings/models":
            self._json(200, list_openai_models())
        elif parsed.path == "/api/app":
            self._json(200, read_app_info())
        elif parsed.path == "/api/update/check":
            from nta_agent import updater
            force = parse_qs(parsed.query).get("force", ["0"])[0] == "1"
            self._json(200, updater.cached_check(force=force))
        elif parsed.path.startswith("/static/"):
            code, ctype, body = serve_static(parsed.path[len("/static/"):])
            self._send(code, body, ctype)
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        cfg = self.server.cfg
        if parsed.path.startswith("/api/agent/"):
            try:  # drain any request body FIRST — replying before reading it lets the
                length = int(self.headers.get("Content-Length", "0"))  # client socket
                if length:                                             # reset (Windows
                    self.rfile.read(length)                           # ConnectionAborted)
            except (ValueError, TypeError):
                pass
            action = parsed.path[len("/api/agent/"):]
            sup = self.server.supervisor
            fn = {"start": sup.start, "stop": sup.stop,
                  "pause": sup.pause, "resume": sup.resume}.get(action)
            if fn is None:
                self._json(404, {"ok": False, "error": "unknown agent action"})
                return
            self._json(200, fn())
            return
        if parsed.path in ("/api/setup/run", "/api/setup/override"):
            body = self._body()
            if body is None:
                return
            from nta_agent.setup import steps
            name = str(body.get("step", ""))
            if name not in steps.STEPS:
                self._json(400, {"ok": False, "error": "bước không hợp lệ"})
                return
            if parsed.path.endswith("override"):
                if name not in steps.OVERRIDABLE:
                    self._json(400, {"ok": False, "error": "bước này không bỏ qua được"})
                    return
                self._json(200, steps.override(name))
                return
            if name in steps.NEEDS_STOPPED and self.server.supervisor.status().get("pid"):
                # would swap config tables / the token file under a running agent
                self._json(409, {"ok": False, "error": "Dừng agent trước khi chạy bước này."})
                return
            self._json(200, steps.run_step(name))
            return
        if parsed.path == "/api/settings":
            body = self._body()
            if body is None:
                return
            r = update_settings(body)
            self._json(200 if r["ok"] else 400, r)
            return
        if parsed.path in ("/api/update/apply", "/api/update/rollback"):
            if self._body() is None:
                return
            from nta_agent import paths, updater
            if not paths.is_packaged():
                self._json(400, {"ok": False, "error": "chỉ dùng được ở bản đóng gói"})
                return
            info = updater.cached_check()
            if parsed.path.endswith("apply") and not info.get("update"):
                self._json(400, {"ok": False, "error": "không có bản cập nhật"})
                return
            self.server.supervisor.stop()
            port = self.server.server_address[1]
            try:
                if parsed.path.endswith("apply"):
                    updater.spawn(port, assets=info["update"]["assets"])
                else:
                    updater.spawn(port, rollback_=True)
            except OSError as e:
                self._json(500, {"ok": False, "error": f"không chạy được updater: {e}"})
                return
            self._json(200, {"ok": True, "restarting": True})
            import os
            import threading
            threading.Timer(0.5, lambda: os._exit(0)).start()  # updater waits for our exit
            return
        if parsed.path == "/api/settings/test-key":
            if self._body() is None:
                return
            self._json(200, test_openai_key())
            return
        if parsed.path in ("/api/lessons/retire", "/api/lessons/pin"):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                lid = str(body["id"])
            except (ValueError, TypeError, KeyError):
                self._json(400, {"ok": False, "error": "need id"})
                return
            from nta_agent.brain.lessons import LessonStore
            store = LessonStore(cfg.lessons_path)
            if parsed.path.endswith("retire"):
                store.retire(lid)
            else:
                store.pin(lid)
            self._json(200, read_lessons(cfg))
            return
        if parsed.path == "/api/forts/decide":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                idx = int(body["index"])
                decision = str(body.get("decision", ""))
            except (ValueError, TypeError, KeyError):
                self._json(400, {"ok": False, "error": "need index + decision"})
                return
            from nta_agent.runtime import fort_decisions
            fort_decisions.update(cfg.fort_decisions_path, idx, decision)
            self._json(200, recompute_forts(cfg))
            return
        if parsed.path == "/api/forge/target":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, TypeError):
                self._json(400, {"ok": False, "error": "bad json"})
                return
            r = set_forge_target(cfg, body if isinstance(body, dict) else {})
            self._json(200 if r["ok"] else 400, r)
            return
        if parsed.path.startswith("/api/dig/"):
            # pick a target / confirm the previewed path / cancel — the agent's
            # DigService does the work (a preview never sends a game command)
            op = parsed.path[len("/api/dig/"):]
            body = {}
            if op == "request":
                body = self._body()
                if body is None:
                    return
            else:
                try:  # drain an optional body (see /api/agent/)
                    length = int(self.headers.get("Content-Length", "0"))
                    if length:
                        self.rfile.read(length)
                except (ValueError, TypeError):
                    pass
            r = dig_command(cfg, op, body)
            self._json(200 if r["ok"] else 400, r)
            return
        if parsed.path == "/api/forts/build":
            # User picked an owned cell in the recommended zone -> enqueue it (validated
            # against the precomputed zone + cap). The FortBuild rule builds it when
            # resources allow, holding normal construction until then.
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                idx = int(body["index"])
            except (ValueError, TypeError, KeyError):
                self._json(400, {"ok": False, "error": "need index"})
                return
            fv = read_forts_view(cfg)
            mw = int(read_territory_view(cfg).get("map_width") or 600)
            zone = {int(y) * mw + int(x) for x, y in (fv.get("fort_zone") or [])}
            cap = int(fv.get("fort_cap") or 0)
            if cap and int(fv.get("fort_count") or 0) >= cap:
                self._json(400, {"ok": False, "error": "đã đủ số Cứ Điểm (đạt giới hạn)"})
                return
            if idx not in zone:
                self._json(400, {"ok": False,
                                 "error": "ô không nằm trong vùng gợi ý (đất mình, ngoài bán kính 6)"})
                return
            from nta_agent.runtime import fort_queue
            fort_queue.add(cfg.pending_forts_path, idx)   # persistent queue, retried
            self._json(200, {"ok": True, "index": idx, "xy": [idx % mw, idx // mw],
                             "queued": True})
            return
        if parsed.path == "/api/chat":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, TypeError):
                self._json(400, {"ok": False, "error": "bad json"})
                return
            msg = str(body.get("message", "")).strip()
            if not msg:
                self._json(400, {"ok": False, "error": "empty message"})
                return
            hist = getattr(self.server, "chat_history", [])
            out = handle_chat(cfg, msg, history=hist)
            # Keep BOTH sides: user-only history showed the LLM the same request again,
            # unanswered — live 2026-09-25 it then asked back or mapped IMP to the
            # wrong pawn type 5/5 times.
            self.server.chat_history = (hist + [{"role": "user", "content": msg},
                                                {"role": "assistant",
                                                 "content": chat_reply_summary(out)}])[-8:]
            self._json(200 if out.get("ok") else 503, out)
            return
        if parsed.path == "/api/chat/confirm":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                renames = body.get("renames") or []
                strike = body.get("strike_target") or []
            except (ValueError, TypeError, AttributeError):
                self._json(400, {"ok": False, "error": "bad json"})
                return
            if strike:
                self._json(200, confirm_strike(cfg, strike))
                return
            self._json(200, confirm_renames(cfg, renames))
            return
        if parsed.path == "/api/profile":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, TypeError):
                self._json(400, {"ok": False, "error": "bad json"})
                return

            def _ints(v):
                out = []
                for x in v if isinstance(v, list) else []:
                    try:
                        out.append(int(x))
                    except (TypeError, ValueError):
                        pass
                return out

            # Build the edit from what the panel actually sent. The BuildOrderPanel
            # posts {order, skip} at top level; other panels post a nested section
            # ({leveling:{...}}, {logistics:{...}}, ...). Previously this hardcoded
            # edits={build:{order,skip}} for EVERY post — so a leveling/logistics
            # save was dropped AND it wiped build.order/skip to empty.
            edits: dict = {}
            if "order" in body or "skip" in body:
                edits["build"] = {"order": _ints(body.get("order", [])),
                                  "skip": _ints(body.get("skip", []))}
            for key in ("build", "leveling", "logistics", "occupy", "army",
                        "revive", "forge", "notes"):
                if key in body:
                    edits[key] = body[key]
            self._json(200, handle_profile_edit(cfg, edits))
            return
        if parsed.path != "/api/command":
            self._json(404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, TypeError):
            self._json(400, {"ok": False, "error": "bad json"})
            return
        action = body.get("action")
        if action == "equip":
            if (not body.get("pawn_id") and body.get("pawn_id") != 0) or not body.get("equip_uid"):
                self._json(400, {"ok": False, "error": "equip needs pawn_id + equip_uid"})
                return
            cmd = {"action": "equip", "pawn_id": int(body["pawn_id"]),
                   "equip_uid": str(body["equip_uid"]),
                   "skin_id": int(body.get("skin_id", 0) or 0),
                   "attack_speed": int(body.get("attack_speed", 0) or 0)}
            cid = append_command(cfg.commands_path, cmd)
            self._json(200, {"ok": True, "id": cid})
            return
        track = body.get("track")
        if action not in ("select", "reroll") or track not in _VALID_TRACK:
            self._json(400, {"ok": False, "error": "bad action/track"})
            return
        if action == "select" and "ceri_id" not in body:
            self._json(400, {"ok": False, "error": "select needs ceri_id"})
            return
        cmd = {"action": action, "track": track, "lv": int(body.get("lv", 0) or 0)}
        if action == "select":
            cmd["ceri_id"] = int(body["ceri_id"])
        cid = append_command(cfg.commands_path, cmd)
        self._json(200, {"ok": True, "id": cid})


def serve(cfg: RuntimeConfig, port: int, *, host: str = "127.0.0.1") -> DashboardServer:
    return DashboardServer((host, port), Handler, cfg)
