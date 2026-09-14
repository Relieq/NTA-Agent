# Track B (Brain) — Architecture + B1 Tactics Profile — Design

Date: 2026-09-14
Status: Approved (brainstorming) → ready for implementation plan (B1)
Owner: NTA-Agent execution (profile/heuristics) + (later) brain/

## 1. Problem & philosophy

The hands layer (rules + sim-advisor) plays deterministically with zero LLM
tokens and is validated (sim matches 15/15 real battles). What's missing is the
**strategy layer**: long-term, adaptive decisions. Per ROADMAP and the user's
three principles:

- **Deterministic-first** — rules decide wherever possible; the LLM is sparse.
- **Sim-as-advisor** — the battle sim answers "can we win / how much loss".
- **Profile-as-contract, chat-as-author, thin brain** — a persisted **tactics
  profile** is the single source of truth the hands obey; the brain (LLM) and
  chat only **author/tune the profile**, never drive taps/API directly.

So the "brain" is thin: it edits a profile; the hands execute it.

## 2. Track B decomposition (each its own spec → plan)

- **B1 — Tactics Profile (this spec):** the contract. A schema'd, persisted
  profile the hands read every tick; deterministic; no LLM. Delivers a
  configurable agent immediately and is the foundation for B2–B4.
- **B2 — Intents layer:** formal high-level intents + resolver (intent→actions),
  the brain↔hands contract for anything not expressible as profile state.
- **B3 — Brain loop (LLM) + policies:** sparse Claude calls at decision points
  that read `GameState` and **propose profile edits** (thin brain); token budget
  + guardrails.
- **B4 — Chat-with-brain:** converse to adjust strategy; edits land in the
  profile.

This spec designs the Track B architecture and details **B1** only.

## 3. B1 — Tactics Profile

### 3.1 Schema & storage

A persisted JSON profile with sane defaults, loaded each tick, editable by hand
/ dashboard now and by brain/chat later. Location: `build/run/profile.json`
(runtime, gitignored) with defaults from a checked-in template. Two domains:

```jsonc
{
  "army": {
    "group": ["<armyUid>", ...],          // the fixed attack group (order = preference)
    "roles": { "<armyUid>": "archer|tank" },
    "onetile": true,                        // prefer 1-tile ordering (archers first) vs avoid
    "composition": { "<armyUid>": { "pawnId": count, ... } }  // recruit targets
  },
  "occupy": {
    "max_loss": 0,          // occupy only if sim-predicted loss% <= this (0 = no losses)
    "max_march_ms": 0,      // 0 = no limit; else skip cells whose march exceeds this
    "loot": {               // chest optimization
      "enabled": true,
      "min_reward_per_chest": 0   // skip cells whose reward/chest-cost ratio is below this
    }
  }
}
```

`max_loss` alone handles dangerous monsters: the sim reuses the real engine, so
reflect/thorns are already reflected in the predicted loss — a reflect monster
that would cost troops yields a high loss% and is filtered out. (Adaptive tactics
for special monsters — swapping lifesteal/heal gear, sending a heal-tank — is a
**future** enhancement, not B1.)

### 3.2 Chest / treasure mechanic (RE first — B1 task 1)

Occupying a resource cell awards treasures (chests) onto pawns; you then
open/claim them, subject to a capacity budget. Confirmed surface: config
`treasure.json` / `land.json` / `landAttr.json`; APIs `OpenArmyTreasure` /
`ClaimArmyTreasure` / `OpenArmysTreasure` (batch); `ArmyTreasuresInfo{armyUid,
pawnTreasures}`. **RE to confirm** (per the user):

- Per-cell chest **cost** and reward (from `landAttr`/`treasure`/`land`).
- Capacity model per room type: newbie/ranked = **+50/day, capped at 50** when
  current < 50; free mode = **unlimited but bounded by empty pawn treasure
  slots**. Where current capacity/slots are read in `GameState`.
- The open→claim flow + which action the agent calls.

This RE output defines the exact fields the occupy planner reads; it is the first
task of B1 and gates 3.3's loot optimization.

### 3.3 Occupy-farming planner (deterministic, profile-driven)

Enhance `OccupyCell` from "attack one winnable cell" into a farming planner:

1. Discover reachable resource cells (existing discovery).
2. For each cell: predict outcome with the sim (existing v2 advisor: picks the
   army group + selection order that wins with least loss). Keep only cells with
   `loss% <= profile.occupy.max_loss` and `march <= max_march_ms`.
3. Score by **loot value per chest cost** (reward / chest-cost), using the RE'd
   treasure model; drop cells below `min_reward_per_chest`.
4. Given the current **chest budget** (capacity or empty pawn slots), pick the
   cell(s) that maximize total reward within budget (greedy by reward/chest, a
   knapsack when needed) — no losses, shortest march as tie-break.
5. Issue the occupy for the chosen cell(s) with the advisor's army order.
6. Separately, a small rule opens/claims earned treasures
   (`OpenArmyTreasure`/`ClaimArmyTreasure`) while budget/slots allow.

The army group + roles come from `profile.army`; the selection order + formation
reuse the existing sim-advisor v2 + formation optimizer.

### 3.4 Army/composition consumers

- `Recruit` fills each profile-group army toward `profile.army.composition`.
- `OccupyCell` uses `profile.army.group`/`roles`/`onetile` to build the candidate
  orders fed to `best_plan` (instead of ad-hoc reachable armies).

### 3.5 Profile access

A small `profile.py`: `load_profile(path) -> Profile` (defaults + file merge),
`save_profile`; a `Profile` dataclass with typed accessors. Rules take the
profile via the runtime wiring (like config today). The dashboard gains a
read/edit view later (B4 territory); B1 ships file + defaults + hand-edit.

## 4. Data flow (B1)

```
profile.json ──load──> Profile
GameState + Profile
  -> Recruit: fill armies to composition
  -> OccupyCell farming planner:
       discover cells -> sim-advisor (group+order, loss<=max_loss)
       -> score by loot/chest (treasure model) -> pick within chest budget
       -> occupy(best order) ; open/claim treasures within budget
```

## 5. Non-goals (B1)

- LLM/brain (B3), chat (B4), intents formalization (B2).
- Build-order / auto-unlock / auto-policy — stay as-is (human-in-loop).
- Adaptive gear/tactics vs special monsters (future).
- Free-mode-specific tuning beyond respecting empty treasure slots.

## 6. Testing

- `profile.py` — defaults + file merge + typed access (pure).
- Chest model reader — parses treasure/landAttr into (cost, reward) per cell
  (pure, against config fixtures).
- Farming planner — pure over injected predict + treasure model: filters by
  max_loss/march, scores by loot/chest, respects chest budget, picks best;
  falls back gracefully when the treasure model is unavailable.
- Recruit-to-composition — fills toward targets.
- Live (manual): verify treasure open/claim + capacity read against the real
  account (RE validation).
- Full Python suite + ruff; existing sim/advisor goldens stay green.
