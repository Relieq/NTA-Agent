from nta_agent.execution.captcha import CaptchaSolver, solve_answer


class FakeConfig:
    def __init__(self):
        self._t = {"antiCheat": {
            10: {"id": 10, "item_1": 1, "item_2": 0, "item_3": 0},
            11: {"id": 11, "item_1": 0, "item_2": 1, "item_3": 0},
            12: {"id": 12, "item_1": 0, "item_2": 0, "item_3": 1},
        }}

    def table(self, name):
        return self._t.get(name, {})


def test_solve_answer_picks_matching_category():
    assert solve_answer("item_2", [10, 11, 12], FakeConfig()) == 11
    assert solve_answer("item_3", [10, 11, 12], FakeConfig()) == 12


def test_solve_answer_fallback_when_no_match_or_malformed():
    assert solve_answer("item_5", [10, 11], FakeConfig()) == 10   # none match -> first
    assert solve_answer("weird", [10, 11], FakeConfig()) == 10    # malformed -> first
    assert solve_answer("item_1", [], FakeConfig()) == 0          # empty -> 0


class FakeActions:
    def __init__(self, question):
        self._q = question
        self.answered = None

    def get_anticheat_question(self):
        return self._q

    def answer_anticheat(self, answer):
        self.answered = answer
        return {"rst": True, "wrongCount": 0}


def test_solver_gets_question_and_answers_correct():
    act = FakeActions({"item": "item_3", "options": [10, 11, 12], "surplusTime": 30})
    res = CaptchaSolver(act, FakeConfig()).solve()
    assert act.answered == 12
    assert res["rst"] is True
