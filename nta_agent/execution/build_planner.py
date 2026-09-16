"""Pick the next building upgrade to perform, config- and prereq-aware.

Buildings in NTA gate on prerequisites (``prep_cond``) and can't exceed the main
hall's level, which is why a fixed build order is natural. This planner walks a
priority order and returns the first step that is *actionable now*: not maxed,
within the main-hall cap, prerequisites met, and affordable. Prereq types we
can't verify locally are left for the server to reject (the rule handles that).
"""
from __future__ import annotations

from dataclasses import dataclass

from nta_agent.data.config import GameConfig
from nta_agent.state.schema import Building, GameState

MAIN_HALL_ID = 2001


@dataclass
class BuildAction:
    kind: str          # "construct" | "upgrade"
    build_id: int
    up: object         # BuildUpgrade for the target level
    build: object = None  # existing Building (upgrades); None for constructs
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


def next_build_action(
    state: GameState,
    config: GameConfig,
    sequence: list[int] | None = None,
    blocked: set | None = None,
    skip: set | None = None,
    room_type: int | None = None,
) -> BuildAction | None:
    """The next build action — construct a new building (lv1) or upgrade one.

    For each id in the order: if the instance count is below ``max_count`` and a
    fresh lv1 is unlocked/affordable/not-blocked, construct it; otherwise fall
    through to upgrading an existing instance (as :func:`next_upgrade`).
    """
    if not state.builds:
        return None
    if len(state.build_queue) >= state.build_queue_slots:
        return None
    blocked = blocked or set()
    skip = set(skip or ())
    # mode-gated buildings for the wrong room type are excluded like skip.
    in_city = set(config.in_city_build_ids(room_type))
    if room_type is not None:
        skip = skip | (set(config.in_city_build_ids()) - in_city)
    queued_uids = {str(q.get("uid", "")) for q in state.build_queue}
    level_by_id = {b.id: b.lv for b in state.builds}
    main_lv = level_by_id.get(MAIN_HALL_ID, 0)
    counts: dict[int, int] = {}
    for b in state.builds:
        counts[b.id] = counts.get(b.id, 0) + 1
    # Default order also covers not-yet-built in-city types, so new buildings get
    # constructed (existing-only order would never reach an unbuilt type).
    order = sequence or sorted(set(counts) | in_city)

    # Construct-first: build every eligible missing/allowed building before
    # spending on upgrades (upgrades would otherwise starve construction).
    for build_id in order:
        if build_id in skip:
            continue
        if (counts.get(build_id, 0) < config.max_count(build_id)
                and ("construct", build_id) not in blocked):
            up1 = config.build_upgrade(build_id, 1)
            if (up1 is not None and _prep_ok(up1.prep_cond, level_by_id)
                    and _affordable(up1.cost, state)
                    and (build_id == MAIN_HALL_ID or main_lv >= 1)):
                return BuildAction(kind="construct", build_id=build_id, up=up1)

    for build_id in order:
        if build_id in skip:
            continue
        for build in [b for b in state.builds if b.id == build_id]:
            if build.uid in queued_uids:
                continue
            target = build.lv + 1
            if (build.uid, target) in blocked:
                continue
            if build_id != MAIN_HALL_ID and target > main_lv:
                continue
            up = config.build_upgrade(build_id, target)
            if up is None or not _prep_ok(up.prep_cond, level_by_id) \
                    or not _affordable(up.cost, state):
                continue
            return BuildAction(kind="upgrade", build_id=build_id, up=up, build=build)
    return None
