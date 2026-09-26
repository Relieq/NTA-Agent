"""world_random.json: this match's exclusive effect pools, cached for rules + dashboard."""
from nta_agent.runtime import world_random


class Acts:
    def __init__(self):
        self.n = 0

    def get_world_random_info(self):
        self.n += 1
        return {"exclusive": {6101: [21, 3]}, "pawn_cost": {3305: 40}}


def test_refresh_writes_and_load_reads_int_keys(tmp_path):
    p = tmp_path / "world_random.json"
    assert world_random.load(p) == {}
    world_random.refresh(Acts(), p)
    assert world_random.load(p) == {6101: [21, 3]}


def test_refresh_is_throttled(tmp_path):
    p = tmp_path / "world_random.json"
    acts = Acts()
    world_random.refresh(acts, p, now=1000.0)
    world_random.refresh(acts, p, now=1000.0 + 60, every_s=3600)
    assert acts.n == 1
    world_random.refresh(acts, p, now=1000.0 + 3601, every_s=3600)
    assert acts.n == 2


def test_refresh_failure_keeps_the_last_file(tmp_path):
    p = tmp_path / "world_random.json"
    world_random.refresh(Acts(), p, now=0.0)

    class Boom:
        def get_world_random_info(self):
            raise RuntimeError("down")
    world_random.refresh(Boom(), p, now=99999.0)
    assert world_random.load(p) == {6101: [21, 3]}
