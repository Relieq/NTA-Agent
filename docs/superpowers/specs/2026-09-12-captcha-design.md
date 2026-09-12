# Captcha (anti-cheat) Auto-Handling (Chặng 2D) — Design

Date: 2026-09-12
Status: Approved (brainstorming) → ready for implementation plan
Parent: Chặng 2, sub-project 2D (final piece; depends on 2A spine)

## 1. Problem

The game periodically challenges the player with an anti-cheat captcha after a
number of actions. Until handled, every further action fails, stalling the
autonomous loop. 2D detects the captcha and solves it automatically so the agent
keeps running unattended. This is the concrete Chặng-2 test criterion: **catch
the captcha** (detect it) — and, since it is deterministic, solve it too.

## 2. Game mechanic (RE, verified)

- **Trigger:** any action reply returns error `ecode.500221` (`ecode.ANTI_CHEAT`).
  In this codebase `GameClient.request` raises `ApiError("<route>: <error>")`, so a
  captcha surfaces as an `ApiError` whose message contains `"ecode.500221"`.
- **Question:** `game/HD_GetAntiCheatQuestion{}` → `{item: string, options: int32[],
  surplusTime: int32}`. `item` is `"item_1".."item_5"` naming the target pawn
  category; `options` are `antiCheat.json` row ids (each row = a pawn art `icon` +
  category flags `item_1..item_5`).
- **Answer:** the correct option is the one whose `antiCheat.json` row has
  `item_<N> == 1` for the question's `N`. Submit `game/HD_AntiCheatAnswer{answer:
  int32}` (the chosen option id) → `{rst: bool, wrongCount, notPassCount,
  surplusTime}`. `rst == true` means passed.
- Deterministic: the answer is derivable from config — no image recognition or
  human input required.

## 3. Chosen approach (decisions locked)

- **Auto-solve, in-process.** The captcha is deterministic, frequent, and blocks
  the loop, so the agent solves it itself (no vision, no human-decision queue).
- **Detect at the rule-engine boundary.** `RuleEngine.tick` already catches each
  rule's exception; when the error carries `ecode.500221`, it raises a typed
  `CaptchaRequired` that bubbles to the `Agent`, which solves it and continues
  (the interrupted rule simply retries next tick).
- **Config-driven answer** from `antiCheat.json` via a pure `solve_answer`.

## 4. Architecture

### 4.1 `execution/captcha.py`
- `ANTI_CHEAT_ECODE = "ecode.500221"`.
- `class CaptchaRequired(Exception)` — raised when an action hit the captcha.
- `solve_answer(item: str, options: list[int], config) -> int` — pure:
  `i = int(item.split("item_")[1])`; return the first `option` id whose
  `config.table("antiCheat").get(option)["item_<i>"] == 1`; if none match, return
  `options[0]` (best-effort; a wrong answer just re-challenges next tick).
- `class CaptchaSolver` — `__init__(self, actions, config)`; `solve() -> dict`:
  `q = actions.get_anticheat_question()`; `ans = solve_answer(q["item"],
  q["options"], config)`; `return actions.answer_anticheat(ans)`.

### 4.2 `execution/actions.py` (+2 thin methods)
- `get_anticheat_question() -> dict` — `game/HD_GetAntiCheatQuestion{}`.
- `answer_anticheat(answer: int) -> dict` — `game/HD_AntiCheatAnswer{answer}`.

### 4.3 `execution/heuristics.py` (detection)
- In `RuleEngine.tick`'s per-rule `except`, before recording the generic error:
  if `ANTI_CHEAT_ECODE in str(e)` → `raise CaptchaRequired(str(e)) from e` (bubble
  out of `tick`). All other errors are recorded as today (`name!ERR:detail`).

### 4.4 `execution/agent.py` (solve)
- `Agent` gains an optional `captcha` attribute (a `CaptchaSolver` or None).
- `Agent.tick` wraps `engine.tick(...)` in `try/except CaptchaRequired`: on catch,
  if a solver is set → `result = self.captcha.solve()`, emit
  `captcha_solved`/`captcha_failed` (from `result["rst"]`), return
  `["captcha_solved"]`; if no solver → emit `captcha_detected`, return
  `["captcha_detected"]`. The main `run` loop is unchanged (it still calls `tick`).

### 4.5 `runtime/runner.py` (wiring)
- When building the agent and `GameConfig.load()` succeeds, set
  `agent.captcha = CaptchaSolver(agent.actions, config)` (reuse the config already
  loaded for `DecisionService`). If config is missing, leave it None (captcha is
  still detected and logged, just not auto-solved).

## 5. Data flow

```
rule acts → action raises ApiError("...: ecode.500221")
RuleEngine.tick → detects 500221 → raise CaptchaRequired
Agent.tick → catch → CaptchaSolver.solve():
    get_anticheat_question() → {item, options}
    solve_answer(item, options, config) → answer id (antiCheat[id][item_N]==1)
    answer_anticheat(answer) → {rst, wrongCount, ...}
  → emit captcha_solved/failed → return ["captcha_solved"]
next tick: the interrupted rule retries normally
```

## 6. Error handling

- Wrong answer (`rst == false`) → logged; the next action re-challenges and the
  solver runs again (natural retry through the loop). No infinite tight loop —
  one solve attempt per tick.
- `GetAntiCheatQuestion`/`AntiCheatAnswer` transport errors propagate as normal
  transient errors to `Agent.run`'s existing recovery.
- No solver / no config → captcha is still detected and surfaced
  (`captcha_detected` event); the loop does not die.
- Unparseable `item` → `solve_answer` falls back to `options[0]`.

## 7. Testing

- **solve_answer:** picks the option whose `item_<N>` flag is 1 (fake config);
  falls back to `options[0]` when none match or `item` is malformed.
- **CaptchaSolver.solve:** fake `actions` returns a question; asserts
  `answer_anticheat` is called with the correct id and the reply is returned.
- **RuleEngine detection:** a rule raising `ApiError("x: ecode.500221")` makes
  `tick` raise `CaptchaRequired`; a rule raising a different ecode still records
  `name!ERR:...` (no raise).
- **Agent.tick:** with a rule that hits 500221 and a fake solver → returns
  `["captcha_solved"]` and the solver was called; with no solver → returns
  `["captcha_detected"]`; a normal tick is unaffected.

## 8. Out of scope

- Vision-based captcha solving (unneeded — deterministic from config).
- Surfacing the captcha to the human (auto-solve is correct here).
- 2E (gear assignment + forge), which remains a separate later sub-project.

This completes Chặng 2 (spine + dashboard + decision-queue + captcha).
