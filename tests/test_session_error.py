from nta_agent.io.api.client import ApiError, NotConnected, is_session_error


def test_session_errors_detected():
    assert is_session_error(NotConnected("down")) is True
    assert is_session_error(TimeoutError()) is True
    assert is_session_error(ConnectionError()) is True
    assert is_session_error(ApiError("game/HD_GetPlayerArmys: Service(type:game) not found")) is True


def test_ecode_is_not_session_error():
    assert is_session_error(ApiError("game/HD_DrillPawn: ecode.500054")) is False
    assert is_session_error(ApiError("game/HD_AddAreaBuild: ecode.500034")) is False
    assert is_session_error(ValueError("boom")) is False


def test_engine_reraises_session_error_for_recovery():
    from types import SimpleNamespace

    from nta_agent.execution.heuristics import RuleEngine

    class DownRule:
        name = "down"
        def applies(self, state, actions):
            raise ApiError("game/HD_GetPlayerArmys: Service(type:game) not found")
        def act(self, actions):
            pass

    eng = RuleEngine(rules=[DownRule()])
    try:
        eng.tick(SimpleNamespace(), SimpleNamespace())
        assert False, "expected session error to propagate"
    except ApiError as e:
        assert is_session_error(e)


def test_engine_swallows_normal_ecode():
    from types import SimpleNamespace

    from nta_agent.execution.heuristics import RuleEngine

    class EcodeRule:
        name = "ec"
        def applies(self, state, actions):
            raise ApiError("game/HD_DrillPawn: ecode.500054")
        def act(self, actions):
            pass

    fired = RuleEngine(rules=[EcodeRule()]).tick(SimpleNamespace(), SimpleNamespace())
    assert any(f.startswith("ec!ERR") for f in fired)  # swallowed as rule error
