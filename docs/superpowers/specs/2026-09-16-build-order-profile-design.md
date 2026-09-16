# Build-order in the profile (user/brain/chat-tunable) — Design

Date: 2026-09-16
Status: Approved (brainstorming) → ready for implementation plan
Owner: NTA-Agent execution (profile/build_planner/heuristics) + brain

## 1. Problem

C1 constructs + upgrades buildings, but the priority is a fixed sorted-by-id
order. That upgrades buildings the user considers low-value early (e.g. Tường
Thành 2000) before economy buildings. The old bot let the user edit a static
`build_order` list. We can do better: make the build order a **profile field**,
so it is authored by the user (hand/dashboard), by chat, and by the brain — one
list, three sources — reusing the B1/B4 machinery.

## 2. Decision (locked)

Add `profile.build`:
- **`order`**: list of build ids in priority. Ids in the list are prioritized in
  that sequence; ids not listed fall to the end (existing sorted default). Applies
  to **both** construction and upgrades.
- **`skip`**: list of build ids the agent never auto-constructs or upgrades
  (e.g. `[2000]` to leave Tường Thành alone).

Keep **construct-first** (build every eligible not-skipped building, in order,
before upgrading). Deterministic hands; brain/chat only edit the list.

## 3. Effective order

`BuildOrder` computes the sequence it hands `next_build_action`:
`order` (as given) followed by every other in-city / existing build id sorted,
with `skip` ids removed. `next_build_action` already walks a sequence
construct-first then upgrade; `skip` filtering happens before it (the ids never
enter the sequence).

## 4. Components

| File | Change |
|---|---|
| `execution/profile.py` | `DEFAULT_PROFILE["build"] = {"order": [], "skip": []}`; `Profile` gains `build: dict`; `load_profile`/`save_profile` carry it; `apply_edits` merges `build.order`/`build.skip` (replace-list semantics, like `notes`). |
| `execution/build_planner.py` | `next_build_action(..., skip=None)` — skip ids are excluded from both the construct and upgrade passes. (Order still comes via `sequence`.) |
| `execution/heuristics.py` (`BuildOrder`) | When a profile is present, build the effective sequence from `profile.build.order` (+ remaining sorted) and pass `profile.build.skip` to `next_build_action`. Without a profile, behavior is unchanged (sorted default). `BuildOrder` gains an optional `profile`. |
| `execution/heuristics.py` (`RuleEngine.default`) | Pass `profile` to `BuildOrder(profile=profile)` (like Recruit/OccupyCell). |
| `brain/guard.py` | Sanitize `build`: `order`/`skip` = lists of ints that are real in-city build ids (drop unknown). Needs the set of valid build ids — pass `valid_build_ids` into `sanitize_edits` (from config), or validate against a provided set. |
| `brain/llm.py` | `_SYSTEM` documents `build.order` / `build.skip`. |
| `brain/digest.py` | Include `profile.build` so the brain sees the current order. |
| `dashboard/server.py` (`handle_chat`) | Provide valid build ids (from `GameConfig.in_city_build_ids()`) to the guard so chat can edit build order. |

**Guard valid-ids source:** `sanitize_edits(edits, profile, valid_army_uids,
valid_build_ids=None)` — when `valid_build_ids` is None, `build` edits are
dropped (safe default); callers that can supply it (BrainService, handle_chat)
pass `set(config.in_city_build_ids())`.

## 5. Data flow

```
profile.build = {order:[...], skip:[...]}   (user / chat / brain author it)
BuildOrder.applies:
  seq = order + sorted(remaining in-city/existing ids), minus skip
  next_build_action(state, config, sequence=seq, blocked, skip=skip)
    construct-first over seq (skip excluded) -> else upgrade over seq
```

## 6. Error handling / edge

- No profile → BuildOrder uses the current sorted default (unchanged).
- Empty `order` → pure sorted default (current behavior).
- `skip` a building that exists → it is never upgraded (left as-is); already-built
  instances stay.
- Guard drops non-int / unknown build ids; a fully-invalid `build` edit = no
  change.

## 7. Non-goals

- Separate construct-order vs upgrade-order (one list governs both).
- Per-preset build orders (build order is city-global, not tied to formations).
- Outside-city construction (C2).
- Auto-derived "smart" default order (the brain can tune the list; the rule stays
  deterministic).

## 8. Testing

- `profile` — defaults have `build.order/skip`; `apply_edits` merges them
  (replace-list).
- `build_planner.next_build_action` — `skip` excludes ids from construct + upgrade;
  `sequence` order respected.
- `BuildOrder` — with a profile: prioritizes `order`, skips `skip` (e.g. skip 2000
  → never upgrades wall even when eligible); without a profile: unchanged.
- `guard.sanitize_edits` — `build.order/skip` kept only for valid build ids;
  dropped when `valid_build_ids` absent; junk removed.
- `handle_chat` — a "reorder build" instruction produces a `build` edit (fake llm).
- Full Python suite + ruff.
