import pytest

from nta_agent.execution.captcha import CaptchaRequired
from nta_agent.execution.heuristics import RuleEngine


class Rule:
    def __init__(self, name, err):
        self.name = name
        self._err = err

    def applies(self, state, actions):
        return True

    def act(self, actions):
        raise RuntimeError(self._err)


def test_anti_cheat_error_raises_captcha_required():
    eng = RuleEngine(rules=[Rule("recruit", "game/HD_DrillPawn: ecode.500221")])
    with pytest.raises(CaptchaRequired):
        eng.tick(None, None)


def test_other_error_is_recorded_not_raised():
    eng = RuleEngine(rules=[Rule("recruit", "game/HD_DrillPawn: ecode.500033")])
    fired = eng.tick(None, None)
    assert fired == ["recruit!ERR:ecode.500033"]
