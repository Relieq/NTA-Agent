"""Pick the next building upgrade to perform, config- and prereq-aware.

Buildings in NTA gate on prerequisites (``prep_cond``) and can't exceed the main
hall's level, which is why a fixed build order is natural. This planner walks a
priority order and returns the first step that is *actionable now*: not maxed,
within the main-hall cap, prerequisites met, and affordable. Prereq types we
can't verify locally are left for the server to reject (the rule handles that).
"""
from __future__ import annotations

from nta_agent.data.config import GameConfig
from nta_agent.state.schema import Building, GameState

MAIN_HALL_ID = 2001
_PREP_NEED_BUILDING = 4  # prep_cond "4,<buildId>,<lv>": need that building at <lv>


def parse_prep_cond(s: str) -> tuple[int, int, int] | None:
    parts = (s or "").split(",")
    if len(parts) >= 3:
        return int(parts[0]), int(parts[1]), int(parts[2])
    return None


def _prep_ok(prep_cond: str, level_by_id: dict[int, int]) -> bool:
    """True if the prerequisite is met. Only the building-level type (4) is checked
    locally; other types default to True and rely on server validation."""
    cond = parse_prep_cond(prep_cond)
    if not cond:
        return True
    ctype, param, value = cond
    if ctype == _PREP_NEED_BUILDING:
        return level_by_id.get(param, 0) >= value
    return True


def _affordable(cost: dict[str, int], state: GameState) -> bool:
    r = state.resources
    have = {"cereal": r.cereal, "timber": r.timber, "stone": r.stone, "iron": r.iron}
    return all(have.get(res, 0) >= amt for res, amt in cost.items())


def next_upgrade(
    state: GameState,
    config: GameConfig,
    sequence: list[int] | None = None,
    blocked: set[tuple[str, int]] | None = None,
) -> tuple[Building, object] | None:
    """Return (building, BuildUpgrade) for the next actionable upgrade, or None.

    ``blocked`` is a set of (uid, target_lv) the server has recently rejected
    (conditions we can't verify locally); those steps are skipped.
    """
    if not state.builds:
        return None
    # Respect build-queue capacity: don't start more than the slots allow.
    if len(state.build_queue) >= state.build_queue_slots:
        return None
    blocked = blocked or set()
    queued_uids = {str(q.get("uid", "")) for q in state.build_queue}
    level_by_id = {b.id: b.lv for b in state.builds}
    main_lv = level_by_id.get(MAIN_HALL_ID, 0)

    order = sequence or sorted({b.id for b in state.builds})
    # index buildings by id preserving instances (walls/towers can repeat)
    by_id: dict[int, list[Building]] = {}
    for b in state.builds:
        by_id.setdefault(b.id, []).append(b)

    for build_id in order:
        for build in by_id.get(build_id, []):
            if build.uid in queued_uids:
                continue  # already upgrading
            target = build.lv + 1
            if (build.uid, target) in blocked:
                continue  # server rejected this step recently
            # non-main buildings can't exceed the main hall's level
            if build_id != MAIN_HALL_ID and target > main_lv:
                continue
            up = config.build_upgrade(build_id, target)
            if up is None:
                continue  # maxed / no such level
            if not _prep_ok(up.prep_cond, level_by_id):
                continue
            if not _affordable(up.cost, state):
                continue
            return build, up
    return None
