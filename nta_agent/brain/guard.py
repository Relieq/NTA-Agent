"""Validate + clamp LLM-proposed profile edits before applying."""
from __future__ import annotations

import re
import types
import unicodedata

_ROLES = {"archer", "tank"}
_EXPANSION = {"none", "spiral", "octopus", "hybrid"}
_OCCUPY_ORDER = {"auto", "tank_first", "dps_first"}
_LESSON_TRIGGER_KEYS = {"monster_id", "resource", "goal"}


def _num(v, lo, hi, default):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _formation(f: dict, valid: set) -> dict:
    """Validate one formation (group/roles/onetile/composition) against real uids."""
    out: dict = {}
    if isinstance(f.get("group"), list):
        out["group"] = [str(u) for u in f["group"] if str(u) in valid]
    if isinstance(f.get("roles"), dict):
        out["roles"] = {str(u): r for u, r in f["roles"].items()
                        if str(u) in valid and r in _ROLES}
    if "onetile" in f:
        out["onetile"] = bool(f["onetile"])
    if isinstance(f.get("composition"), dict):
        comp: dict = {}
        for u, targets in f["composition"].items():
            if str(u) in valid and isinstance(targets, dict):
                comp[str(u)] = {str(pid): int(_num(c, 0, 10 ** 6, 0))
                                for pid, c in targets.items()}
        out["composition"] = comp
    return out


def sanitize_edits(edits: dict, profile, valid_army_uids, valid_build_ids=None) -> dict:
    valid = {str(u) for u in (valid_army_uids or ())}
    out: dict = {}

    occ_in = edits.get("occupy") if isinstance(edits, dict) else None
    if isinstance(occ_in, dict):
        occ: dict = {}
        if "max_loss" in occ_in:
            occ["max_loss"] = _num(occ_in["max_loss"], 0, 100, profile.occupy["max_loss"])
        if "max_march_ms" in occ_in:
            occ["max_march_ms"] = int(_num(occ_in["max_march_ms"], 0, 10 ** 9, 0))
        if "expansion" in occ_in and str(occ_in["expansion"]) in _EXPANSION:
            occ["expansion"] = str(occ_in["expansion"])
        pol_in = occ_in.get("policy")
        if (isinstance(pol_in, dict) and "order" in pol_in
                and str(pol_in["order"]) in _OCCUPY_ORDER):
            occ["policy"] = {"order": str(pol_in["order"])}
        loot_in = occ_in.get("loot")
        if isinstance(loot_in, dict):
            loot: dict = {}
            if "enabled" in loot_in:
                v = loot_in["enabled"]
                loot["enabled"] = (v.lower() in ("1", "true", "yes")
                                   if isinstance(v, str) else bool(v))
            if "min_reward_per_chest" in loot_in:
                loot["min_reward_per_chest"] = _num(loot_in["min_reward_per_chest"], 0, 10 ** 9, 0)
            if loot:
                occ["loot"] = loot
        if occ:
            out["occupy"] = occ

    army_in = edits.get("army") if isinstance(edits, dict) else None
    if isinstance(army_in, dict):
        army: dict = _formation(army_in, valid)  # flat group/roles/onetile/composition
        # strike_target: the composition goal (list of {pawn_id, armies, size}) the
        # ArmyComposer reconciles toward. Validate shape; [] clears the goal.
        if isinstance(army_in.get("strike_target"), list):
            st = []
            for t in army_in["strike_target"]:
                if isinstance(t, dict) and t.get("pawn_id"):
                    pid = int(_num(t["pawn_id"], 1000, 99999, 0))
                    if pid:
                        st.append({"pawn_id": pid,
                                   "armies": int(_num(t.get("armies", 1), 1, 20, 1)),
                                   "size": int(_num(t.get("size", 9), 1, 9, 9))})
            army["strike_target"] = st
        if isinstance(army_in.get("presets"), dict):
            presets = {str(n): _formation(f, valid) for n, f in army_in["presets"].items()
                       if isinstance(f, dict)}
            if presets:
                army["presets"] = presets
        if "active" in army_in:
            name = str(army_in["active"])
            known = set(army.get("presets") or {}) | set(profile.army.get("presets") or {})
            if name == "" or name in known:
                army["active"] = name
        if army:
            out["army"] = army

    lv_in = edits.get("leveling") if isinstance(edits, dict) else None
    if isinstance(lv_in, dict):
        lv: dict = {}
        if "enabled" in lv_in:
            v = lv_in["enabled"]
            lv["enabled"] = (v.lower() in ("1", "true", "yes")
                             if isinstance(v, str) else bool(v))
        if "target_lv" in lv_in:
            lv["target_lv"] = int(_num(lv_in["target_lv"], 0, 1000, 0))
        if "max_leveling" in lv_in:
            lv["max_leveling"] = int(_num(lv_in["max_leveling"], 1, 50, 1))
        if lv:
            out["leveling"] = lv

    rev_in = edits.get("revive") if isinstance(edits, dict) else None
    if isinstance(rev_in, dict) and "enabled" in rev_in:
        v = rev_in["enabled"]
        out["revive"] = {"enabled": (v.lower() in ("1", "true", "yes")
                                     if isinstance(v, str) else bool(v))}

    lg_in = edits.get("logistics") if isinstance(edits, dict) else None
    if isinstance(lg_in, dict):
        lg: dict = {}
        if "enabled" in lg_in:
            v = lg_in["enabled"]
            lg["enabled"] = (v.lower() in ("1", "true", "yes")
                             if isinstance(v, str) else bool(v))
        if "target" in lg_in:
            lg["target"] = int(_num(lg_in["target"], 1, 50, 9))
        if "heal_skip_frac" in lg_in:
            lg["heal_skip_frac"] = _num(lg_in["heal_skip_frac"], 0, 1, 0.2)
        if "min_shortfall" in lg_in:
            lg["min_shortfall"] = int(_num(lg_in["min_shortfall"], 1, 50, 1))
        if isinstance(lg_in.get("exclude"), list):
            lg["exclude"] = [str(u) for u in lg_in["exclude"] if str(u) in valid]
        # redeploy: only known army uids -> a positive cell index
        if isinstance(lg_in.get("redeploy"), dict):
            rd = {}
            for uid, idx in lg_in["redeploy"].items():
                if str(uid) in valid:
                    n = int(_num(idx, 0, 10 ** 9, 0))
                    if n > 0:
                        rd[str(uid)] = n
            lg["redeploy"] = rd
        if lg:
            out["logistics"] = lg

    if isinstance(edits.get("advice"), list):
        advice = []
        for a in edits["advice"]:
            if isinstance(a, dict) and str(a.get("text", "")).strip():
                advice.append({"text": str(a["text"]).strip()[:200],
                               "why": str(a.get("why", "")).strip()[:200]})
        if advice:
            out["advice"] = advice[:10]

    if isinstance(edits.get("notes"), list):
        out["notes"] = [str(s).strip()[:200] for s in edits["notes"] if str(s).strip()][:20]

    # build.order/skip (the dashboard edits this; the brain must NOT — it strips
    # build from its own edits before calling here, see BrainService.tick).
    build_in = edits.get("build") if isinstance(edits, dict) else None
    if isinstance(build_in, dict) and valid_build_ids is not None:
        valid_b = {int(x) for x in valid_build_ids}
        b: dict = {}
        for key in ("order", "skip"):
            if isinstance(build_in.get(key), list):
                b[key] = [int(x) for x in build_in[key]
                          if isinstance(x, int) and int(x) in valid_b]
        if b:
            out["build"] = b
    return out


def sanitize_renames(edits, valid_army_uids, dominant_by_uid=None) -> list:
    """Validate chat-proposed army renames into [{uid, name}] ready for the command
    queue. Drops unknown uids and names that break the client rule (empty / >12 /
    newline). On a duplicate uid the LAST rename wins.

    Anti-mis-map: when a rename carries ``pawn`` (the pawn type the model claims the
    army is — e.g. 3206 rìu khiên, 3305 IMP) and ``dominant_by_uid`` is supplied, the
    army's actual dominant pawn MUST equal it, else the rename is DROPPED. This stops
    a weak model from renaming the wrong army (the reported bug)."""
    raw = edits.get("army_renames") if isinstance(edits, dict) else None
    if not isinstance(raw, list):
        return []
    valid = {str(u) for u in (valid_army_uids or ())}
    dom = {str(k): str(v) for k, v in (dominant_by_uid or {}).items()}
    by_uid: dict = {}
    for r in raw:
        if not isinstance(r, dict):
            continue
        uid = str(r.get("uid", ""))
        name = str(r.get("name", "")).strip()
        if uid not in valid or not name or len(name) > 12 or "\n" in name:
            continue
        pawn = r.get("pawn")
        if pawn not in (None, "") and dom and dom.get(uid) != str(pawn):
            continue  # claimed type doesn't match the army's composition -> drop
        by_uid[uid] = name        # last write wins
    return [{"uid": u, "name": n} for u, n in by_uid.items()]


def _safe_lever_edits(lever, valid_army_uids, valid_build_ids) -> dict:
    """Run a lesson's proposed lever edits through the normal edit guard, then drop
    the human-owned parts (build, max_loss, army.group/roles/...) so a lesson can
    only auto-apply the SAME safe levers the brain may edit. army.* (incl.
    strike_target) is dropped: a strike group needs the player's confirmation."""
    dummy = types.SimpleNamespace(occupy={"max_loss": 0}, army={})
    clean = sanitize_edits(lever, dummy, valid_army_uids, valid_build_ids=valid_build_ids)
    clean.pop("build", None)
    clean.pop("advice", None)
    clean.pop("notes", None)
    clean.pop("army", None)  # strike_target needs the player's confirmation, never a lesson
    if isinstance(clean.get("occupy"), dict):
        clean["occupy"].pop("max_loss", None)   # the user's hard risk cap — never a lesson
        if not clean["occupy"]:
            clean.pop("occupy")
    return clean


def sanitize_lessons(edits, ledger, valid_army_uids, valid_build_ids=None) -> list:
    """Validate LLM-proposed lessons into dicts ready for LessonStore.upsert.

    Anti-hallucination: a lesson is DROPPED unless its evidence cites at least one
    event that ``ledger.has(...)`` confirms is real. A resolution that only touches
    human-owned levers (or nothing) is downgraded to advice for the human."""
    raw = edits.get("lessons") if isinstance(edits, dict) else None
    if not isinstance(raw, list):
        return []
    out: list = []
    for le in raw:
        if not isinstance(le, dict):
            continue
        evidence = [str(e) for e in (le.get("evidence") or []) if ledger.has(str(e))]
        if not evidence:
            continue  # grounded-only: no real evidence -> not a lesson
        trig = le.get("trigger") or {}
        match = {k: v for k, v in (trig.get("match") or {}).items()
                 if k in _LESSON_TRIGGER_KEYS}
        trigger = {"kind": str(trig.get("kind", ""))}
        if match:
            trigger["match"] = match
        diagnosis = str(le.get("diagnosis", "")).strip()[:200]
        res_in = le.get("resolution") if isinstance(le.get("resolution"), dict) else {}
        resolution = None
        adv = res_in.get("advice")
        if isinstance(adv, str) and adv.strip():
            resolution = {"advice": adv.strip()[:200]}
        elif isinstance(res_in.get("lever_edits"), dict):
            lever = _safe_lever_edits(res_in["lever_edits"], valid_army_uids, valid_build_ids)
            if lever:
                resolution = {"lever_edits": lever}
        if resolution is None:            # human-owned-only or empty -> advise instead
            if not diagnosis:
                continue
            resolution = {"advice": diagnosis}
        item = {"trigger": trigger, "diagnosis": diagnosis, "resolution": resolution,
                "evidence": evidence}
        if le.get("validated_by"):
            item["validated_by"] = str(le["validated_by"])[:120]
        out.append(item)
    return out[:10]


# ---- rename ambiguity guards (deterministic, after the LLM proposes) ---------------
# Evidence (2026-09-24 eval, memory nta-agent-jev): the chat LLM confidently renames
# the wrong army when (1) the player refers to an army by POSITION ("đội đầu tiên" —
# list order isn't stable in-game) or (2) by a pawn TYPE that several armies share.
_POSITIONAL = re.compile(
    r"\b(dau tien|thu nhat|thu hai|thu ba|thu tu|thu nam|thu \d+|cuoi cung|sau cung"
    r"|tren cung|duoi cung|dau danh sach|cuoi danh sach|ben trai|ben phai)\b")


# "thuần X" / "toàn X" / "pure" = the player wants a PURE-X army ("toàn bộ" = all, not purity)
_PURE = re.compile(r"\b(thuan|pure)\b|\btoan (?!bo\b)")


def _fold(s: str) -> str:
    """Lowercase, strip Vietnamese diacritics (đ -> d)."""
    s = unicodedata.normalize("NFD", str(s or "").lower().replace("đ", "d"))
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def _names_army(instruction_compact: str, name: str) -> bool:
    key = re.sub(r"[^a-z0-9]", "", _fold(name))
    return len(key) >= 2 and key in instruction_compact


def rename_ambiguity(instruction, renames, armies) -> str | None:
    """A clarification question if the proposed renames are unsafe, else None.

    ``renames``: [{uid, name}] (already sanitized). ``armies``: [{uid, name,
    dominant, troops}]. Ask when (3) several armies get the SAME new name. For an army
    the player didn't NAME explicitly, also ask when (1) they pointed by position, or
    (2) another army with the same dominant pawn type exists outside the batch, or
    (4) the army is mixed (the type is < 2/3 of it, or a PURE army was asked for),
    or (5) the player listed more new names than armies were proposed.
    Optional ``share`` per army = dominant pawn count / army size (default 1)."""
    if not renames:
        return None
    by_uid = {str(a.get("uid")): a for a in armies}

    def cand(a):
        return f"• {a.get('name', '?')} — {a.get('troops', '')}"

    # (3) several armies given the SAME new name: almost never intended — the LLM
    # typically answered a singular request by renaming every army of that type.
    seen: dict = {}   # folded name -> (display name, [uids])
    for r in renames:
        shown = str(r.get("name", "")).strip()
        seen.setdefault(shown.lower(), (shown, []))[1].append(str(r.get("uid")))
    dup = next((v for k, v in seen.items() if k and len(set(v[1])) >= 2), None)
    if dup:
        pool = [by_uid[u] for u in dict.fromkeys(dup[1]) if u in by_uid]
        return (f"Bạn muốn đặt CÙNG tên \"{dup[0]}\" cho {len(pool)} đội, hay chỉ một đội? "
                "Nếu một đội thì là đội nào (gọi theo tên đội)?\n"
                + "\n".join(cand(a) for a in pool))
    folded = _fold(instruction)
    # (5) the player listed N new names ("thành A và B", "to A, B") but fewer armies
    # were proposed -> a partial rename (the LLM dropped one) -> ask.
    tail = re.split(r"\bthanh\b|\bto\b", folded)
    if len(tail) >= 2:
        items = [x for x in re.split(r",|;|\bva\b|\bvoi\b|\band\b", tail[-1]) if x.strip()]
        n_armies = len({str(r.get("uid")) for r in renames})
        if len(items) >= 2 and n_armies < len(items):
            pool = [by_uid[u] for u in dict.fromkeys(str(r.get("uid")) for r in renames)
                    if u in by_uid]
            return (f"Bạn nêu {len(items)} tên mới nhưng tôi mới xác định được {n_armies} đội. "
                    "Bạn muốn đổi tên những đội nào (gọi theo tên đội)?\n"
                    + "\n".join(cand(a) for a in pool))
    compact = re.sub(r"[^a-z0-9]", "", folded)
    batch = {str(r.get("uid")) for r in renames}
    unnamed = [by_uid[u] for u in batch
               if u in by_uid and not _names_army(compact, by_uid[u].get("name", ""))]
    if not unnamed:
        return None
    if _POSITIONAL.search(folded):
        doms = {str(a.get("dominant")) for a in unnamed}
        pool = [a for a in armies if str(a.get("dominant")) in doms]
        return ("Bạn chỉ đội theo vị trí, nhưng thứ tự đội trong game không cố định nên "
                "tôi không chắc là đội nào. Bạn muốn đổi tên đội nào (gọi theo tên đội)?\n"
                + "\n".join(cand(a) for a in pool))
    pure_req = bool(_PURE.search(folded))
    for a in unnamed:
        share = float(a.get("share", 1.0) or 0.0)
        # (4) referenced by TYPE but the army is mixed: that type is < 2/3 of it, or
        # the player asked for a PURE army and this one isn't.
        if share < 2 / 3 - 1e-9 or (pure_req and share < 1.0 - 1e-9):
            return ("Đội này là đội LAI, không thuần loại lính bạn nói — tôi không chắc đúng "
                    "đội bạn muốn. Bạn muốn đổi tên đội nào (gọi theo tên đội)?\n" + cand(a))
    for a in unnamed:
        peers = [b for b in armies if str(b.get("dominant")) == str(a.get("dominant"))
                 and str(b.get("uid")) not in batch
                 and (not pure_req or float(b.get("share", 1.0) or 0.0) >= 1.0 - 1e-9)]
        if peers:
            pool = [a, *peers]
            return ("Có nhiều đội cùng loại lính khớp mô tả của bạn, tôi không chắc đội nào. "
                    "Bạn muốn đổi tên đội nào (gọi theo tên đội)?\n"
                    + "\n".join(cand(b) for b in pool))
    return None


# A soldier count the player gave explicitly ("mỗi đội 5 lính", "3 con") — only then
# may an army be smaller than full.
_SOLDIER_COUNT = re.compile(r"\b\d+\s*(linh|con|nguoi|quan|pawn|soldier)")
_FULL_ARMY = 9


def sanitize_strike(strike, unlocked, instruction: str, pawn_names: dict | None = None,
                    trust_size: bool = False):
    """Validate a chat-proposed ``army.strike_target`` BEFORE it is shown for
    confirmation. Returns ``(clean, notes)``:

    * pawn types that aren't unlocked (``unlocked`` = set of ids; ``None`` = unknown,
      keep all) are dropped with a note — unlocks reset when the main city is
      re-created, so the LLM must never assume a type (live: 'khiên lớn' -> locked 3206);
    * ``size`` is a full army (9) unless the instruction states a soldier count
      (live: the LLM invented size 1);
    * optional ``names`` (the names the player gave this entry's armies, in order) are
      trimmed to 12 chars and capped to ``armies``;
    * each entry gets a readable ``name`` (pawn type) for the confirm card.
    """
    names = pawn_names or {}
    # trust_size: re-validating an already-confirmed proposal (size was settled then)
    explicit_size = trust_size or bool(_SOLDIER_COUNT.search(_fold(instruction)))
    clean, notes = [], []
    for t in strike if isinstance(strike, list) else []:
        if not (isinstance(t, dict) and t.get("pawn_id")):
            continue
        pid = int(_num(t["pawn_id"], 1000, 99999, 0))
        if not pid:
            continue
        label = names.get(pid) or f"lính {pid}"
        if unlocked is not None and pid not in unlocked:
            notes.append(f"{label} ({pid}) chưa mở khoá — bỏ khỏi nhóm.")
            continue
        armies = int(_num(t.get("armies", 1), 1, 20, 1))
        size = int(_num(t.get("size", _FULL_ARMY), 1, _FULL_ARMY, _FULL_ARMY))
        if not explicit_size:
            size = _FULL_ARMY
        entry = {"pawn_id": pid, "armies": armies, "size": size, "name": label}
        given = [str(n).strip()[:12] for n in (t.get("names") or [])
                 if isinstance(n, (str, int)) and str(n).strip()]
        if given:
            entry["names"] = given[:armies]
        clean.append(entry)
    return clean, notes
