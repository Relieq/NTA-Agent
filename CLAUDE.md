# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

NTA-Agent is an autonomous agent that plays the Android game **Ninety Thousand Acres**
(`twgame.global.acers`, a Cocos2d-x/JS 4X strategy game) running in BlueStacks. It is a
ground-up rewrite of the older, vision-only bot [NTA-AutoBot](https://github.com/Relieq/NTA-AutoBot).
The repository is currently **greenfield**: the only substantive file is `docs/ROADMAP.md`, which
is the source of truth for architecture and phasing. Read it before making design decisions.

## Core architecture: "hands vs brain" over a hybrid I/O layer

The design (chosen deliberately — see `docs/ROADMAP.md`) has three layers. Understanding the
separation between them is essential and must be preserved as code is added:

- **I/O layer (hybrid):** two interchangeable adapters feed one normalized `GameState`.
  - *API adapter* — reads/sends the game's own network requests (HTTPS). Preferred where the
    protocol has been reverse-engineered.
  - *Vision adapter* — OpenCV template matching + OCR to read the screen, ADB taps to act. The
    fallback that is always available, ported from the old bot's `DeviceManager`/`VisionManager`.
- **Execution layer ("hands"):** deterministic rule/heuristic engine + predictors (battle-outcome,
  build-ROI). Runs the day-to-day loop with **zero LLM tokens**. It translates high-level *intents*
  into concrete action sequences and self-verifies outcomes.
- **Strategy layer ("brain"):** the LLM (Claude) makes sparse, high-level decisions (long-term
  build order, troop allocation, alliance/diplomacy, target selection).

**The load-bearing rule: the LLM never calls tap/API directly.** It only reads the normalized
`GameState` and emits schema'd high-level intents (e.g. `{"action":"attack","target":"tile:x,y",...}`).
The hands layer resolves intents into actions. This keeps token cost low and behavior auditable.

Because reverse-engineering the API is incremental and risky, the system is **API-first with vision
fallback**: crack a domain → use API for it; everything else keeps running on vision. Never let an
API-migration break the vision path for a feature.

## Environment (verified 2026-09-01 — re-verify before relying on)

- Game `twgame.global.acers` **v4.4.0**; engine is **Cocos2d-x JavaScript**
  (`org.cocos2dx.javascript.AppActivity`) — game logic/protocol live in a JS bundle inside
  `base.apk/assets` (typically jsc-compiled or XXTEA-encrypted).
- Emulator: BlueStacks_nxt, Android 9, x86_64, screen **1600x900**, density 240. Combat/coordinate
  math in the old bot assumes 1600x900 — keep that assumption or make it explicit.
- ADB binary: `C:\Program Files\BlueStacks_nxt\HD-Adb.exe` (not on PATH). Device `emulator-5554`,
  adb port **5555** (read from `C:\ProgramData\BlueStacks_nxt\bluestacks.conf`).
- The game speaks **HTTPS (443)**, so intercepting the protocol requires installing the mitmproxy
  CA in the emulator **and** bypassing certificate pinning with Frida.

Common ADB probes (quote the path — it contains a space):
```bash
ADB="/c/Program Files/BlueStacks_nxt/HD-Adb.exe"
"$ADB" devices
"$ADB" shell wm size
"$ADB" exec-out screencap -p > screen.png
```

## Reusing the old bot

The old repo's function set is the idea reference, not the code style. Reusable pieces:
`DeviceManager` (ADB tap/swipe/drag/screenshot), `VisionManager` (multi-scale/multi-channel
template matching with JSON threshold profiles), the map/combat/builder logic, and the
config-driven pattern (`template_profiles.json`, `combat_timing.json`, `build_order`). Its
weaknesses to fix: rigid scripting, unreliable OCR, no accurate state, no API access.

## Build/lint/test

Python 3.12 in a venv at `.venv`. Use the venv interpreter explicitly (Windows):

```bash
.venv/Scripts/python.exe -m pytest -q                 # full suite
.venv/Scripts/python.exe -m pytest tests/test_occupy_rule.py::test_occupy_rule_skips_when_no_stamina -q  # single test
.venv/Scripts/python.exe -m ruff check nta_agent tests # lint
```

### Battle simulator sidecar (Node)

`tools/battlesim/` reuses the game's own battle engine headlessly to predict
occupy/attack outcomes (see `docs/superpowers/specs/2026-09-11-battle-simulator-design.md`).
It requires **Node.js ≥ 18** and reads the (gitignored) decrypted engine + config **by path**:

- `NTA_ENGINE_JS` (default `tools/re/decrypted/index.js`) — decrypted game bundle.
- `NTA_CONFIG_DIR` (default `nta_agent/data/config`) — extracted config tables.

```bash
node tools/battlesim/run-once.js                       # smoke: one known forecast
# --test-force-exit: the engine boot leaves handles open, so node won't exit on its own.
node --test --test-force-exit tools/battlesim/test/golden.test.js  # JS golden/determinism/oracle
node --test --test-force-exit tools/battlesim/test/server.test.js  # sidecar JSON-RPC
```

Python reaches it through `SimBattlePredictor` (`nta_agent/execution/predictors/`),
which spawns the sidecar via `SimBridge`. If Node or the engine is absent, occupy
falls back to the stats predictor — the loop never dies. The Python↔engine
integration test is skipped unless Node + the engine are present.

## Workflow notes

- Superpowers plugin (v6.3.0) is installed. Use its `brainstorming` → `write-plan` →
  `execute-plan` flow to develop each roadmap phase; use `systematic-debugging` and `TDD` skills
  as they apply.
- Commit proactively at logical checkpoints (green tests, a completed unit of work) with clear
  messages; no need to ask first. Still branch before committing on the default branch (`master`).
  Do not push or force-push unless asked.
- Templates/asset names and much of the roadmap are in Vietnamese; match the user's language.
