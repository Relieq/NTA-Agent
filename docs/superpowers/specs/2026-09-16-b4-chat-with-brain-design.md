# B4 — Chat-with-Brain + named presets & strategy notes — Design

Date: 2026-09-16
Status: Approved (brainstorming) → ready for implementation plan
Owner: NTA-Agent dashboard + brain/ + execution (profile) + runtime

## 1. Problem

B3 gives a sparse autonomous brain that edits the profile on a timer. B4 adds a
**dashboard chat box** where the user tells the brain what to do in natural
language and the brain translates that into **profile edits** (thin brain,
profile-as-contract). It also gives the profile a durable **memory** so named
strategies survive and are recalled:

- **Named formation presets** — "create a formation 'turtle': 1 shield + 4 IMP",
  then later "use turtle". Structured, reusable by the hands.
- **Strategy notes** — free-form durable guidance the brain always considers
  ("vs reflect-damage monsters, send a heal-tank, not archers"; "early game
  prioritize timber"). Unstructured; only the brain reads them (the deterministic
  hands still act on structured fields only).

Without this, each brain call is stateless — a named tactic told once is
forgotten. Memory lives in the **profile**, not in chat history.

## 2. Decisions (locked)

- Chat lives in the **dashboard** (new `/api/chat` + a chat box); reuses the
  existing command channel to reach a running agent.
- Chat **only edits the profile** (no Q&A, no streaming).
- Durable memory = **profile**: add `army.presets` + `army.active` (named
  formations) and `notes` (free-form list). Chat history is a short in-RAM
  window in the dashboard for multi-turn context only — not persisted.
- All edits pass the existing `guard.sanitize_edits` (extended for the new
  fields) — chat cannot corrupt the profile.

## 3. Profile schema extension (execution/profile.py)

```jsonc
{
  "army": {
    "group": [...], "roles": {...}, "onetile": true, "composition": {...},  // existing (the ACTIVE formation, kept in sync)
    "active": "",            // name of the active preset ("" = use flat group)
    "presets": {             // named formations (durable memory)
      "turtle": {"group": [...], "roles": {...}, "onetile": true, "composition": {...}}
    }
  },
  "occupy": { ... },         // unchanged
  "notes": []                // free-form strategy notes (brain-only)
}
```

- **Active-preset resolution:** a helper `active_formation(profile) -> dict`
  returns `presets[active]` when `active` names a real preset, else the flat
  `army.{group,roles,onetile,composition}`. Consumers call this instead of
  reading `army.group` directly.
- Switching active also copies the preset's fields into the flat `army.*` so the
  existing rules (and the dashboard "Đội quân" view) need no change beyond
  reading through `active_formation`. (Single source: the helper.)
- Defaults add `active: ""`, `presets: {}`, `notes: []` (deep-copied — the B3
  fix).

## 4. Components

| File | Change |
|---|---|
| `execution/profile.py` | Extend `DEFAULT_PROFILE` (active/presets/notes); `active_formation(profile)`; `apply_edits(profile, clean) -> bool` (extracted from BrainService `_apply`, now also merges `presets`/`notes`/`active`). |
| `brain/guard.py` | Sanitize the new fields: `army.active` (str; only if it names a known/edited preset), `army.presets` (each preset validated like a formation — real army uids, roles, counts), `notes` (list of short strings, capped count/length). |
| `brain/llm.py` | `propose(digest, profile, instruction=None, history=None)` — include the user instruction + short history in the prompt; schema text documents presets/active/notes. |
| `brain/digest.py` | Include `presets` names + `active` + `notes` so the brain "remembers". |
| `runtime/brain_service.py` | Use `profile.apply_edits` (shared helper) instead of its private `_apply`. |
| `runtime/decision_service.py` | Handle a new command `{action:"profile_edit", edits:{...}}` → `apply_edits` into the **live** Profile (DecisionService gains a `profile` ref from the runner). |
| `runtime/runner.py` | Pass the shared `profile` to `DecisionService`. |
| `dashboard/server.py` | `POST /api/chat {message}`: load profile.json + valid army uids (armies.json), `llm.propose(digest, profile, instruction=message, history=window)`, `guard.sanitize_edits`, `apply_edits` into a loaded copy, `save_profile`, append `{action:"profile_edit", edits}` to commands.jsonl, return `{applied, rationale, notes, presets}`. Keeps a small in-RAM history. No key → 503 with a friendly message. |
| `dashboard/page.py` | A chat panel: input + last-N exchanges; shows the applied edit + rationale; a read-only view of current `active`/`presets`/`notes`. |
| `execution/heuristics.py` | `OccupyCell`/`Recruit` read `active_formation(profile)` instead of `profile.army["group"]` directly. |

## 5. Data flow

```
dashboard chat: POST /api/chat {message}
  load profile.json ; valid_uids from armies.json
  edits = brain.llm.propose(digest, profile, instruction=message, history=window)
  clean = guard.sanitize_edits(edits, profile, valid_uids)
  apply_edits(profile, clean) ; save_profile(profile.json)
  append commands.jsonl {action:"profile_edit", edits:clean}
  -> respond {applied:clean, rationale}
running agent: DecisionService reads the command -> apply_edits(live Profile)
  -> next tick, OccupyCell/Recruit use active_formation(profile)
```

## 6. Error handling

- No `OPENAI_API_KEY` → `/api/chat` returns 503 + message; dashboard shows it;
  agent unaffected.
- LLM/network/parse failure → `/api/chat` returns the error; profile unchanged.
- Sanitizer drops invalid fields; a fully-invalid instruction → no change, and
  the response says "no change applied".
- Cross-process: if the agent isn't running, the profile.json write still
  persists; the agent picks it up on next start (loads profile.json).

## 7. Non-goals

- Q&A / explanations (chat only edits the profile).
- Streaming responses.
- Persisted chat history (short in-RAM window only).
- Occupy-policy presets (deferred; `occupy` stays flat).
- Notes executed by the deterministic hands (brain-only; hands act on structured
  fields).

## 8. Testing

- `profile.active_formation` — returns active preset when set + valid, else flat.
- `profile.apply_edits` — merges occupy/army/presets/notes/active; reports change.
- `guard.sanitize_edits` — new fields: presets validated like formations, active
  only if known, notes capped; junk dropped.
- `brain.llm.propose` — instruction + history reach the prompt (fake chat).
- `dashboard /api/chat` — fake llm: saves profile.json, appends profile_edit
  command, returns applied; no key → 503.
- `decision_service` — applies a `profile_edit` command to the live Profile.
- `OccupyCell`/`Recruit` — use the active preset's group when set.
- Full Python suite + ruff; no live OpenAI in tests.
