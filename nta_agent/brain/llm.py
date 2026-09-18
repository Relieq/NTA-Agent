"""The only module that talks to OpenAI. Injectable ``chat`` for tests."""
from __future__ import annotations

import json
import os
import urllib.request


class BrainUnavailable(Exception):
    """No API key / provider unreachable — the brain is skipped this tick."""


_SYSTEM = (
    "You tune a strategy game agent by editing its tactics PROFILE. You never "
    "control the game directly. Return ONLY a JSON object with the profile fields "
    "to change and a short 'rationale'. Schema:\n"
    '{"army":{"group":[armyUid],"roles":{armyUid:"archer|tank"},"onetile":bool,'
    '"composition":{armyUid:{pawnId:count}}},'
    '"occupy":{"max_loss":0-100,"max_march_ms":int>=0,'
    '"expansion":"none|spiral|octopus|hybrid",'
    '"loot":{"enabled":bool,"min_reward_per_chest":number>=0}},'
    '"revive":{"enabled":bool},'
    '"advice":[{"text":"...","why":"..."}]}\n'
    "Only include fields you want to change. max_loss is the max acceptable "
    "predicted troop-loss % for occupying a cell (0 = never lose troops).\n"
    "advice is human-facing recommendations the PLAYER acts on (you do not): "
    "which pending unlock/policy option to pick (see digest.decisions — reserved "
    "for the human), whether to upgrade storage/tech, attack/defend calls, etc. "
    "Keep each short with a concrete reason; omit advice when nothing is worth "
    "raising.\n"
    "occupy.expansion picks the territory-growth pattern: 'spiral' = each new cell "
    "touches one owned cell (single-file, low exposure, easy to defend — use when "
    "the enemy is near); 'octopus' = grab easy cells / reach toward resource-rich "
    "land fast; 'hybrid' = mix; 'none' = plain loot-first. Use territory.enemy_cells "
    "/ territory.nearest_enemy_dist to decide (near enemy -> spiral, safe -> octopus).\n"
    "revive.enabled toggles auto-reviving dead pawns (costs resources); disable it "
    "when resources are tight (see digest.injured for dead-pawn count).\n"
    "army.presets is a map of named formations you can create/recall; set "
    "army.active to a preset name to make it the active formation. notes is a "
    "list of durable free-form strategy reminders you should keep and consider.\n"
    "build.order is the building priority (list of build ids, high priority first) "
    "and build.skip lists build ids to never auto-build/upgrade."
)


def _parse_json(text: str) -> dict:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t[3:]
        if t.lower().startswith("json"):
            t = t[4:]
        t = t.split("```", 1)[0]
    try:
        obj = json.loads(t.strip())
        return obj if isinstance(obj, dict) else {}
    except (ValueError, TypeError):
        return {}


def propose(digest: dict, profile, chat=None, instruction=None, history=None) -> dict:
    chat = chat or default_chat()
    user = ("CURRENT PROFILE:\n"
            + json.dumps({"army": profile.army, "occupy": profile.occupy,
                          "notes": profile.notes})
            + "\n\nGAME STATE:\n" + json.dumps(digest))
    messages = [{"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user}]
    for h in (history or []):
        if isinstance(h, dict) and h.get("role") and h.get("content"):
            messages.append({"role": h["role"], "content": str(h["content"])})
    if instruction:
        messages.append({"role": "user", "content": "INSTRUCTION: " + str(instruction)})
    return _parse_json(chat(messages))


def default_chat():
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise BrainUnavailable("OPENAI_API_KEY not set")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    def chat(messages):
        body = json.dumps({"model": model, "messages": messages, "temperature": 0.2,
                           "response_format": {"type": "json_object"}}).encode("utf-8")
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions", data=body,
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]

    return chat
