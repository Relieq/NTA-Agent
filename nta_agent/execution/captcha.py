"""Detect + auto-solve the anti-cheat captcha (deterministic from antiCheat.json)."""
from __future__ import annotations

ANTI_CHEAT_ECODE = "ecode.500221"


class CaptchaRequired(Exception):
    """An action hit the anti-cheat captcha (ecode.500221)."""


def solve_answer(item: str, options: list[int], config) -> int:
    """The option id whose antiCheat row has item_<N> == 1; options[0] fallback."""
    try:
        n = int(str(item).split("item_")[1])
    except (IndexError, ValueError):
        return options[0] if options else 0
    table = config.table("antiCheat")
    key = f"item_{n}"
    for opt in options:
        row = table.get(opt) or {}
        if row.get(key) == 1:
            return opt
    return options[0] if options else 0


class CaptchaSolver:
    def __init__(self, actions, config):
        self.actions = actions
        self.config = config

    def solve(self) -> dict:
        q = self.actions.get_anticheat_question()
        answer = solve_answer(q.get("item", ""), q.get("options", []) or [], self.config)
        return self.actions.answer_anticheat(answer)
