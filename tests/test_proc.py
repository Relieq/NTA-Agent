import os

from nta_agent.runtime.proc import pid_alive


def test_pid_alive_true_for_self():
    assert pid_alive(os.getpid()) is True


def test_pid_alive_false_for_unused():
    assert pid_alive(2_000_000_000) is False


def test_pid_alive_false_for_nonpositive():
    assert pid_alive(0) is False and pid_alive(-1) is False
