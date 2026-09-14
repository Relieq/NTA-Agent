# B3 — Brain Loop (LLM authors the profile) — Design

Date: 2026-09-14
Status: Approved (brainstorming) → ready for implementation plan
Owner: NTA-Agent brain/ + runtime

## 1. Problem

B1 built the tactics profile (the contract the hands obey). B3 adds the **thin
brain**: a sparse LLM that periodically reads a compact game summary and
**proposes edits to the profile** (occupy/farming policy + army composition).
The hands keep playing deterministically from the profile; the LLM never taps or
calls the game API — it only authors profile state. This realizes the ROADMAP
strategy layer at low, bounded token cost.

Provider: **OpenAI** (per the user; the agent's brain, not this CLI). The
integration is isolated so the provider can change without touching the rest.

## 2. Decisions (locked)

- Brain authors **both** occupy/farming policy and army group/composition.
- **Sparse periodic** cadence (every N ticks) with a hard token/call budget.
- Output = **profile edits (JSON)**, validated + clamped before applying.
- B2 (intents layer) is **skipped** — a thin brain that edits the profile does
  not need per-decision intents yet.

## 3. Architecture

A `BrainService` runs in the tick loop (like `DecisionService`), but sparsely.
When it fires: summarize state → ask the LLM for profile edits → sanitize →
**mutate the live `Profile` in place** (so rules see it next tick) → persist →
emit a `brain_plan` event. Any failure (no key, network, bad output) is caught;
the deterministic hands keep running.

```
tick → policies.should_call(tick, calls) ?
  → digest(state, profile)            # compact, token-cheap
  → llm.propose(digest, profile, chat) # OpenAI JSON structured output
  → guard.sanitize_edits(edits, profile)  # schema + clamp; drop junk
  → apply in place to Profile + save_profile + emit brain_plan
rules (OccupyCell/Recruit) read the updated Profile on the following ticks
```

## 4. Components (each testable in isolation)

| File | Responsibility |
|---|---|
| `nta_agent/brain/digest.py` | `digest(state, profile) -> dict`: compact summary — resources (+rates), armies with composition vs targets, phase signals (main-city lv, army count/strength), recent occupy/farm outcomes. Pure; small. |
| `nta_agent/brain/llm.py` | **Only file that knows OpenAI.** `propose(digest, profile, chat=None) -> dict`: build system+user messages (game context + the profile JSON schema + constraints + "return only a JSON object of edits"), call `chat(messages) -> str`, parse the JSON. `chat` is **injectable**; the default builds an OpenAI caller from env (`OPENAI_API_KEY`, `OPENAI_MODEL` default `gpt-4o-mini`) via the `openai` SDK if present else raw HTTPS, using JSON response format. No key → raise `BrainUnavailable`. |
| `nta_agent/brain/guard.py` | `sanitize_edits(edits, profile) -> dict`: keep only known fields; clamp ranges (`occupy.max_loss` 0–100, `max_march_ms` ≥0, `loot.min_reward_per_chest` ≥0, `loot.enabled` bool; `army.composition` counts ≥0; `army.group`/`roles` only real army uids present in state); drop everything else. Pure. |
| `nta_agent/brain/policies.py` | `BrainPolicy(every_ticks:int, max_calls:int)`; `should_call(tick, calls_made) -> bool` (fires on the cadence until the budget is exhausted). Pure. |
| `nta_agent/runtime/brain_service.py` | `BrainService(profile, cfg, on_event, llm=None, policy=None)`; `tick(state)`: gate on policy → digest → llm.propose → guard → apply-in-place + `save_profile(profile, cfg.profile_path)` + emit `brain_plan{changed, rationale}`; swallow `BrainUnavailable`/errors. Holds the **same** `Profile` object the rules use. |
| `runtime/runner.py` | Build `BrainService` with the shared profile; call `service.tick(state)` in `on_tick` (after DecisionService). |
| `runtime/config.py` | `brain_every_ticks` / `brain_max_calls` from env (`NTA_BRAIN_EVERY`, `NTA_BRAIN_MAX_CALLS`), defaults e.g. 60 ticks / 50 calls. |

**Live-profile update:** the rules hold the `Profile` object; `BrainService`
mutates `profile.army`/`profile.occupy` **dicts in place** (never replaces the
object), so edits are visible without re-wiring. Persisted for restarts.

## 5. LLM contract

- **System prompt:** who the agent is, the 3 principles (thin brain edits
  profile only), the profile JSON schema with field meanings + valid ranges, and
  "respond with ONLY a JSON object containing the fields to change and a short
  `rationale` string."
- **User prompt:** the `digest` JSON + the current profile JSON.
- **Response:** JSON — a partial profile (`army`/`occupy` subsets) + `rationale`.
  Parsed leniently (strip code fences); malformed → treated as no-op.
- **Determinism/cost:** `temperature` low; response bounded; one call per fire;
  budget capped. The digest is small to keep input tokens low.

## 6. Error handling

- Missing `OPENAI_API_KEY` → `BrainUnavailable` → BrainService no-ops (logged
  once); hands unaffected.
- Network/parse/timeout → caught; profile unchanged that tick.
- Sanitizer rejects out-of-range/unknown → those fields dropped; valid ones still
  apply. A fully-invalid edit = no-op.

## 7. Companion: auto open/claim treasures (deterministic hands rule)

Added to this batch (was a B1 follow-up). This is a **hands rule**, not brain —
it closes the farming loop: after occupying cells, collect the earned chests.

- **Detection:** scan `get_player_armys()` (or the city area) for pawns whose
  `treasures` field is non-empty. An unopened treasure has empty `rewards`;
  an opened one has `rewards` (pending claim). `PlayerInfo.hasNewTreasure` is a
  cheap gate to skip the scan.
- **Actions (batch):** `open_armys_treasure(targets)` /
  `claim_armys_treasure(targets)` → routes `game/HD_OpenArmysTreasure` /
  `game/HD_ClaimArmysTreasure` with `targets = [{index, auid}, …]`
  (`ArmyTreasureTarget`). Per-army `open_army_treasure`/`claim_army_treasure`
  already exist as the fallback.
- **Rule `ClaimTreasures`:** when `hasNewTreasure` or any army has pending
  treasures → build targets for those armies → open (unopened) then claim.
  **Budget-aware:** open at most `chest_budget(state)` chests (unlimited sentinel
  on the novice/free account). Best-effort: batch-result errors (e.g. `500076`
  already-opened) are ignored; never blocks the loop.
- Wired into `RuleEngine.default` alongside the other rules.
- **Live-validation caveat:** the exact per-army index + budget consumption is
  confirmed against the real account when available; the rule is guarded so a
  wrong assumption degrades to a no-op rather than a failure.

## 8. Non-goals (B3)

- Interactive chat with the brain (B4).
- B2 intents layer (dropped).
- Build-order / auto-unlock authoring — profile scope stays army + occupy.
- Multi-provider abstraction beyond the injectable `chat` seam.

## 9. Testing

- `ClaimTreasures` — fake actions: armies with pending pawn `treasures` → builds
  the right `targets` and calls open then claim (batch); no pending → no call;
  respects the chest budget; batch errors swallowed.
- `digest` — pure: state+profile → expected compact dict (no network).
- `guard.sanitize_edits` — clamps ranges, drops unknown fields / fake army uids,
  keeps valid; fully-invalid → `{}`.
- `policies.should_call` — fires on cadence, stops at budget.
- `llm.propose` — inject a fake `chat` returning JSON (and JSON in code fences);
  asserts the messages include the schema + digest, and parses edits; no real
  OpenAI call.
- `BrainService.tick` — fake llm: applies sanitized edits to the shared Profile
  in place + persists + emits `brain_plan`; respects cadence/budget; swallows
  `BrainUnavailable`.
- Full Python suite + ruff; no live OpenAI in tests.
