from nta_agent.execution.heuristics import FortBuild


class Acts:
    def __init__(self, raise_ecode=None):
        self.built = []
        self._raise = raise_ecode

    def create_city(self, index, build_id):
        if self._raise:
            raise RuntimeError(f"game/HD_CreateCity: ecode.{self._raise}")
        self.built.append((index, build_id))
        return {"rst": True}


def _rule(queue, **kw):
    removed = []
    r = FortBuild(pending_source=lambda: list(queue),
                  remove_fn=lambda i: removed.append(i), **kw)
    r._removed = removed
    return r


def test_builds_pending_fort_and_removes_on_success():
    r = _rule([331273])
    acts = Acts()
    assert r.applies(None, acts) is True
    r.act(acts)
    assert acts.built == [(331273, 2102)]     # FORT_BUILD_ID
    assert r._removed == [331273]             # dropped from queue on success


def test_keeps_in_queue_on_insufficient_resources():
    r = _rule([331273])
    acts = Acts(raise_ecode="500012")
    r.applies(None, acts)
    r.act(acts)
    assert r._removed == []                    # stays queued to retry later
    assert r._cooldown > 0                     # backs off, no spam
    # while cooling down it does not act
    assert r.applies(None, acts) is False


def test_drops_on_permanent_error():
    r = _rule([331273])
    acts = Acts(raise_ecode="500034")          # e.g. cap / invalid -> don't jam queue
    r.applies(None, acts)
    r.act(acts)
    assert r._removed == [331273]


def test_no_pending_does_not_apply():
    assert _rule([]).applies(None, Acts()) is False
