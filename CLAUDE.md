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

## Environment (LDPlayer since 2026-09-10 — re-verify before relying on)

- **Emulator: LDPlayer 9** (v9.5.31.0, Android 9, x86_64), NOT BlueStacks. Switched from
  BlueStacks because LDPlayer's 1-click root is far easier (root confirmed: `su -c id` → uid=0).
  BlueStacks is kept only as a cold fallback. See memory `nta-agent-lab-setup`.
- **ADB binary: `D:\LDPlayer\LDPlayer9\adb.exe`** (device `emulator-5554`, also `127.0.0.1:5555`).
  Do NOT use `C:\Program Files\BlueStacks_nxt\HD-Adb.exe` — its adb client (v36) mismatches
  LDPlayer's adb server (v41) and spams "server version mismatch" + restarts the daemon every call.
  LDPlayer CLI: `D:\LDPlayer\LDPlayer9\ldconsole.exe` (`modify --resolution/--root/...`).
- Game `twgame.global.acers` **v4.4.4** on LDPlayer (newer than the old v4.4.0 BlueStacks build),
  defaults to **English** (`__slg_lang__=en`); engine is **Cocos2d-x JavaScript**
  (`org.cocos2dx.javascript.AppActivity`) — logic/protocol in a JS bundle inside `base.apk/assets`
  (jsc-compiled + XXTEA-encrypted; decrypt with `tools/re/decrypt_jsc.py`).
- Screen: the game **hard-locks portrait 900x1600** on LDPlayer (ADB/autorotate can't force it).
  The old bot's 1600x900 combat/coordinate math is therefore outdated — the project is API-first,
  so pixel math is being retired; don't assume 1600x900.
- Protocol is **MQTT over TLS 1.2** to `nine-hk.twomiles.cn:3653` (payload is app-layer protobuf,
  XXTEA key `2d5e8a49-a7f8-43`), not plain HTTPS. Intercepting needs Frida (TLS + pin bypass);
  the RE lab (frida-server, tcpdump) is already set up — see `nta-agent-lab-setup` / `nta-agent-re-findings`.
- **The agent connects to the game API directly (MQTT), not through ADB** — so which emulator is up
  doesn't affect the agent loop; ADB is only for the vision fallback + manual inspection (screenshots).
  Single game session: when the agent logs in it KICKS the emulator client, so close the agent before
  reading the game UI, and vice-versa.

Common ADB probes (quote the path — it contains a space; do NOT prefix `MSYS_NO_PATHCONV` unless a
`/sdcard/...` arg gets mangled, in which case use a `//sdcard/...` double-slash for device paths):
```bash
ADB="/d/LDPlayer/LDPlayer9/adb.exe"
"$ADB" devices
"$ADB" shell wm size
# exec-out screencap can corrupt the PNG on Windows; pull via an on-device file instead:
"$ADB" shell screencap -p //sdcard/s.png && "$ADB" pull //sdcard/s.png ./screen.png && "$ADB" shell rm //sdcard/s.png
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
