"""Deterministic rule engine — the "hands" decide without spending LLM tokens.

A :class:`Rule` inspects :class:`GameState` and, when it applies, performs one
action via :class:`Actions`. The :class:`RuleEngine` runs every applicable rule
per tick (rules must be idempotent). Strategy-level choices (which build order,
whom to attack) belong to the brain, not here — these rules are the routine
housekeeping that keeps the account ticking over.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from nta_agent.execution.actions import Actions
from nta_agent.execution.captcha import ANTI_CHEAT_ECODE, CaptchaRequired
from nta_agent.state.schema import GameState


class Rule(Protocol):
    name: str

    def applies(self, state: GameState, actions: Actions) -> bool: ...
    def act(self, actions: Actions) -> None: ...


def _record_res_block(rule, resource: str | None) -> None:
    """Report a resource-shortage back-off to the failure ledger (F2/brain).

    Best-effort: the runner may set ``rule.ledger``; absent it, this is a no-op.
    ``resource`` is the resource the rule characteristically needs, so the brain's
    digest can aggregate pressure by resource."""
    led = getattr(rule, "ledger", None)
    if led is None:
        return
    try:
        led.record("res_depletion", {"rule": getattr(rule, "name", "?"), "resource": resource})
    except Exception:
        pass  # ledger I/O must never break a rule


def _caps(state: GameState) -> tuple[int, int]:
    """(granaryCap, warehouseCap) from the live player block; 0 if unknown."""
    player = (state.raw or {}).get("player") or {}
    return int(player.get("granaryCap", 0) or 0), int(player.get("warehouseCap", 0) or 0)


@dataclass
class CollectCityOutput:
    """Collect the main city's output while storage has room for it.

    Safe and always beneficial; skipped when storage is at cap (the server would
    reject it anyway) to avoid pointless requests.
    """
    name: str = "collect_city_output"
    fail_cooldown: int = 20    # ticks to wait after a hard rejection before retrying
    max_cooldown: int = 720    # cap on the unclaimable back-off (~1h at 5s ticks)
    _cooldown: int = 0
    _unclaimable: int = 0      # consecutive "nothing to claim" -> escalating wait

    # The server rejects a claim with nothing accrued yet as ecode.500171
    # ("Unclaimable"). It is an expected timing condition, not an error: whether
    # output is ready is not in the state we fetch (no cityOutputMap), so we
    # discover it by trying, then back off progressively so a city that simply has
    # no claimable output goes dormant instead of retrying forever.
    UNCLAIMABLE_ECODE = "ecode.500171"

    def applies(self, state: GameState, actions: Actions) -> bool:
        if self._cooldown > 0:
            self._cooldown -= 1
            return False
        # Resources auto-fill from production (see store.accrue_output) — the agent
        # does NOT need to claim to keep its stock fresh. ClaimCityOutput only
        # gathers any separately-accrued city-output pile; collect it when storage
        # has room. Caps unknown -> skip (don't spam claims; accrual keeps stock
        # fresh regardless).
        granary, warehouse = _caps(state)
        if not (granary or warehouse):
            return False  # caps unknown -> skip; local accrual keeps stock fresh
        r = state.resources
        return (
            (granary and r.cereal < granary)
            or (warehouse and r.timber < warehouse)
            or (warehouse and r.stone < warehouse)
        )

    def act(self, actions: Actions) -> None:
        try:
            actions.collect_city_output()
            self._unclaimable = 0  # a real claim -> reset the back-off
        except Exception as e:
            if self.UNCLAIMABLE_ECODE in str(e):
                # nothing to claim yet — expected; back off progressively, stay quiet
                self._unclaimable += 1
                self._cooldown = min(self.fail_cooldown * 2 ** (self._unclaimable - 1),
                                     self.max_cooldown)
                return
            self._cooldown = self.fail_cooldown  # other rejection -> surface it
            raise


@dataclass
class BuildOrder:
    """Upgrade buildings along a priority order, respecting prereqs and cost.

    ``sequence`` is a list of build ids in priority order (like the old fixed
    build order); when None, all owned buildings are considered lowest-id first.
    Needs the config tables; if they're absent the rule simply never applies.
    """
    name: str = "build_order"
    sequence: list[int] | None = None
    config: object | None = None
    profile: object = None   # tactics profile: build.order / build.skip
    queue_cooldown: int = 24  # back off when the build queue is busy (~2min)
    _pending: object = None  # BuildAction chosen in applies()
    _city: int = 0           # main-city index for construction
    _cooldown: int = 0        # global back-off (queue full / already queued)
    _blocked: set = field(default_factory=set)  # server-rejected steps (2 key shapes)
    _sig: tuple = ()  # last builds signature; changing it clears blocks (retry)

    # Global (not per-build) queue conditions: the drill/recruit task holds the
    # build slot but isn't always synced into our build_queue, so the pre-check
    # passes and the server rejects. Back off quietly instead of churning every
    # tick through the whole build list. 500014 = queue full, 500013 = already queued.
    QUEUE_ECODES = ("ecode.500014", "ecode.500013")

    def _cfg(self):
        if self.config is None:
            from nta_agent.data.config import GameConfig
            try:
                self.config = GameConfig.load()
            except FileNotFoundError:
                self.config = False  # sentinel: unavailable
        return self.config or None

    def applies(self, state: GameState, actions: Actions) -> bool:
        if self._cooldown > 0:
            self._cooldown -= 1
            return False
        cfg = self._cfg()
        if not cfg:
            return False
        # The build queue holds concurrent build/upgrade tasks; when it is full the
        # server rejects any further build with ecode.500014 ("Construction Queue
        # Full"). Skip entirely rather than churn the whole build list against it.
        slots = state.build_queue_slots or 0
        if slots and len(state.build_queue) >= slots:
            return False
        # When any building level changes, retry previously-blocked steps.
        sig = tuple(sorted((b.uid, b.lv) for b in state.builds))
        if sig != self._sig:
            self._sig = sig
            self._blocked.clear()
        from nta_agent.execution.build_planner import next_build_action
        rt = state.room_type
        seq, skip = self.sequence, None
        if self.profile is not None:
            b = self.profile.build
            skip = b.get("skip") or []
            order = list(b.get("order") or [])
            rest = sorted(set(cfg.in_city_build_ids(rt)) | {x.id for x in state.builds})
            seq = order + [i for i in rest if i not in order]
        self._pending = next_build_action(state, cfg, seq, self._blocked, skip=skip,
                                          room_type=rt)
        self._city = state.main_city_index
        return self._pending is not None

    def act(self, actions: Actions) -> None:
        action = self._pending
        self._pending = None
        if action is None:
            return
        try:
            if action.kind == "construct":
                actions.add_build(self._city, action.build_id)
            else:
                actions.upgrade_build(action.build.index, uid=action.build.uid)
        except Exception as e:
            # Queue busy (full / already-queued) is GLOBAL, not this step's fault —
            # back off quietly for the whole queue rather than blocking one id and
            # churning the rest against the same full queue.
            if any(q in str(e) for q in self.QUEUE_ECODES):
                self._cooldown = self.queue_cooldown
                return
            # Otherwise it's a per-step rejection (e.g. 500034 duplicate-not-maxed):
            # block just this step until the builds signature changes, and surface it.
            if action.kind == "construct":
                self._blocked.add(("construct", action.build_id))
            else:
                self._blocked.add((action.build.uid, action.up.level))
            raise


@dataclass
class OccupyCell:
    """Occupy a nearby resource cell the agent can win, spending stamina for loot.

    Discovers candidates around the main city (GetAreaInfo probe), predicts each
    with battle-A, and sends the strongest garrison army at the lowest-loss win.
    Discovery is throttled (it costs one request per probed cell).
    """
    name: str = "occupy_cell"
    radius: int = 2
    min_stamina: int = 1
    discover_every: int = 8   # ticks between discovery sweeps
    fail_cooldown: int = 8
    predictor: object = None
    use_sim: bool = False      # prefer the headless engine sim for the win verdict
    sim: object = None
    on_event: object = None    # optional on_event(kind, detail) to surface the plan
    profile: object = None     # Profile: group + occupy/loot policy (farming)
    config: object = None      # GameConfig for treasure model (lazy)
    _sim_off: bool = False     # sidecar checked and unavailable -> stop retrying
    threats_source: object = None  # callable -> enemy index set (P2 defense); wired in runner
    territory_source: object = None  # callable -> (owned_set, zone_centers) for bridging
    locked_source: object = None   # callable -> army-uid set the ArmyComposer is arranging
    lessons_source: object = None  # callable -> active lessons (Inc 3 contextual recall)
    contest_range: int = 1     # a winnable candidate within this of an enemy is contested
    _pending: object = None    # (armies_list, target_index)
    _rally: object = None       # (armies_to_move, city, for_target) — consolidate then attack
    _heal: object = None        # (army_move, node) — route a wounded army to heal first
    _cooldown: int = 0
    _state_ref: object = None  # stashed for act()'s formation optimization
    _land_ref: int = 0
    _sim_fail: str = ""        # last reason the engine sim was skipped (diagnostic)

    def _pred(self):
        if self.predictor is None:
            from nta_agent.execution.predictors.battle import BattlePredictor
            try:
                self.predictor = BattlePredictor.from_stats()
            except FileNotFoundError:
                self.predictor = BattlePredictor()
        return self.predictor

    def _sim_pred(self):
        """The headless-sim predictor if enabled and the sidecar is reachable."""
        if not self.use_sim or self._sim_off:
            return None
        if self.sim is None:
            from nta_agent.execution.predictors.sim_bridge import get_bridge
            from nta_agent.execution.predictors.sim_predictor import SimBattlePredictor
            if not get_bridge().available():
                self._sim_off = True
                return None
            self.sim = SimBattlePredictor()
        return self.sim

    @staticmethod
    def _dist(a: int, b: int, width: int = 600) -> int:
        return abs(a % width - b % width) + abs(a // width - b // width)

    def _plan_dist(self, plan) -> int:
        """March distance for a plan: from its (co-located) armies to the target.
        Used to prefer a group already near the target over a far one that ties on
        loss — the near group needs no long march or bridging."""
        if not plan.armies:
            return 0
        return self._dist(int(plan.armies[0].get("index", 0) or 0), plan.target)

    def _config(self):
        if self.config is None:
            from nta_agent.data.config import GameConfig
            try:
                self.config = GameConfig.load()
            except FileNotFoundError:
                self.config = False
        return self.config or None

    def _farm_select(self, cands, plans_for, predict, state):
        """Pick the target maximizing loot within the chest budget (profile)."""
        from nta_agent.execution.advisor import best_plan
        from nta_agent.execution.farming import plan_farm
        from nta_agent.execution.treasure_model import cell_loot, chest_budget
        cfg = self._config()
        if cfg is None:  # no treasure model -> fall back to safest win
            return best_plan(cands, plans_for, predict, distance=self._plan_dist)
        occ = self.profile.occupy
        picks = plan_farm(
            cands,
            lambda c: best_plan([c], plans_for, predict, distance=self._plan_dist),
            lambda c: cell_loot(c.land_id, cfg),
            budget=chest_budget(state),
            max_loss=occ.get("max_loss", 0),
            min_reward_per_chest=(occ.get("loot") or {}).get("min_reward_per_chest", 0),
            max_march_ms=occ.get("max_march_ms", 0),
        )
        return picks[0].plan if picks else None

    def _expansion_select(self, cands, plans_for, predict, mode):
        """Pick the winnable target that best fits the expansion pattern.

        Respects the same max_loss cap as farming; ranks survivors by the
        preset's key (spiral: least exposure; octopus: richest land; hybrid).
        """
        from nta_agent.execution.advisor import best_plan
        from nta_agent.execution.expansion import land_value, sort_key
        cfg = self._config()
        max_loss = float(self.profile.occupy.get("max_loss", 0) or 0) if self.profile else 0.0
        scored = []
        for c in cands:
            plan = best_plan([c], plans_for, predict, distance=self._plan_dist)
            if plan is None or not plan.prediction.win:
                continue
            if plan.prediction.loss_percent > max_loss:
                continue
            key = sort_key(mode, owned_neighbors=c.owned_neighbors,
                           land_value=land_value(cfg, c.land_id) if cfg else 0,
                           loss_percent=plan.prediction.loss_percent)
            scored.append((key, plan))
        if not scored:
            return None
        scored.sort(key=lambda t: t[0])
        return scored[0][1]

    def _recall_order(self, cand, default):
        """Inc 3 contextual recall: if an active lesson's trigger matches this cell's
        guardian monster ids and prescribes an attack order, use it here (overriding
        the global occupy.policy.order). Falls back to ``default`` otherwise."""
        if self.lessons_source is None or cand is None or not getattr(cand, "defenders", None):
            return default
        try:
            lessons = self.lessons_source() or []
        except Exception:
            return default
        if not lessons:
            return default
        from nta_agent.brain.lessons import match_lessons
        ids = [int(p.get("id")) for p in cand.defenders if p.get("id")]
        for lz in match_lessons(lessons, {"kind": "battle_loss", "monster_ids": ids}):
            order = ((((lz.resolution or {}).get("lever_edits") or {}).get("occupy") or {})
                     .get("policy") or {}).get("order")
            if order in ("tank_first", "dps_first", "auto"):
                if self.on_event:
                    self.on_event("lesson_recall", {"cell": cand.index, "order": order,
                                                    "lesson": lz.id, "monster_ids": ids})
                return order
        return default

    def _defensive_select(self, cands, plans_for, predict, enemy):
        """P2: when an enemy is contesting a border cell, claim the winnable cell
        nearest the enemy to wall it off (deny the silent creep). Returns a plan or
        None if nothing is contested/winnable."""
        from nta_agent.execution.advisor import best_plan
        w = 600
        epos = [(e % w, e // w) for e in enemy]
        if not epos:
            return None
        best = None
        best_key = None
        for c in cands:
            cx, cy = c.index % w, c.index // w
            edist = min(abs(cx - ex) + abs(cy - ey) for ex, ey in epos)
            if edist > self.contest_range:
                continue  # not contested by an enemy
            plan = best_plan([c], plans_for, predict, distance=self._plan_dist)
            if plan is None or not plan.prediction.win:
                continue
            key = (edist, plan.prediction.loss_percent)  # closest-to-enemy, then safest
            if best_key is None or key < best_key:
                best_key = key
                best = plan
        return best

    def _heal_diversion(self, cands, predict, idle_grp, state):
        """Route a wounded army to heal when its wounds tip its nearest target from
        clean (0-loss) to lossy AND it's convenient (route near, or <4 cells from a
        heal node). Returns (army_move, node_index, name) or None. Cheap: only the
        most-wounded army × its single nearest candidate (2 sims)."""
        if self.territory_source is None or not cands or not idle_grp:
            return None
        from nta_agent.execution.advisor import Plan
        from nta_agent.execution.army_health import army_wound_frac
        from nta_agent.execution.occupy_planner import full_hp_pawns, heal_convenient
        try:
            _owned, centers = self.territory_source()
        except Exception:
            return None
        main = int(state.main_city_index)
        block = {main, main + 1, main + 600, main + 601}
        heal_nodes = [main] + [c for c in centers if c not in block]  # city + forts
        wounded = sorted((a for a in idle_grp if army_wound_frac(a) > 0),
                         key=army_wound_frac, reverse=True)
        for a in wounded:
            ai = int(a.get("index", 0) or 0)
            c = min(cands, key=lambda c: self._dist(ai, c.index))
            if not heal_convenient(ai, c.index, heal_nodes):
                continue
            actual = {"uid": str(a.get("uid")), "index": ai, "pawns": a.get("pawns") or []}
            full = {**actual, "pawns": full_hp_pawns(a.get("pawns") or [])}
            try:
                pa = predict(Plan(armies=[actual], target=c.index, label="heal?", prediction=None))
                pf = predict(Plan(armies=[full], target=c.index, label="heal?", prediction=None))
            except Exception:  # noqa: S112 - a sim hiccup on one army: just skip it
                continue
            actual_clean = bool(pa and pa.win and pa.loss_percent == 0)
            full_clean = bool(pf and pf.win and pf.loss_percent == 0)
            if full_clean and not actual_clean:
                node = min(heal_nodes, key=lambda n: self._dist(ai, n))
                return ({"uid": str(a.get("uid")), "index": ai}, node,
                        a.get("name") or a.get("uid"))
        return None

    def applies(self, state: GameState, actions: Actions) -> bool:
        if state.resources.stamina < self.min_stamina or not state.main_city_index:
            return False
        if self._cooldown > 0:
            self._cooldown -= 1
            return False
        from nta_agent.execution.occupy_planner import discover_around, discover_frontier

        def get_area(i):
            return actions.get_area(i).get("data", {})
        # Primary: follow the OWNED FRONTIER from map chunks (grows with territory,
        # no fixed radius). Fall back to a fixed-radius probe around the city + idle
        # armies only if the chunk scan fails or yields no frontier.
        cands = []
        try:
            from nta_agent.execution.territory import scan_map
            frontier = scan_map(actions, state.main_city_index, state.user.uid).get("frontier")
            if frontier:
                cands = discover_frontier(get_area, frontier, state.user.uid)
        except Exception:
            frontier = None
        if not frontier:  # scan unavailable -> radius fallback around city + idle armies
            from nta_agent.execution.army_health import is_idle as _idle
            centers = {state.main_city_index}
            try:
                centers |= {int(a.get("index", 0) or 0)
                            for a in actions.get_player_armys() if _idle(a)}
            except Exception:
                pass
            cands = discover_around(get_area, centers, self.radius, state.user.uid)
        self._cooldown = self.discover_every  # throttle regardless of outcome
        predictor = self._pred()      # stats: fallback verdict
        sim = self._sim_pred()        # engine: authoritative win verdict when available
        from nta_agent.execution.advisor import Plan, best_plan
        from nta_agent.execution.order_strategies import colocated_orders
        from nta_agent.execution.predictors.sim_bridge import SimUnavailable

        cand_by_index = {c.index: c for c in cands}

        def plans_for(i):
            # Candidate selection-orders from the active formation group (or all reachable).
            # Only IDLE armies can be sent (skip marching/fighting/recruiting/leveling).
            # Origin distance does NOT matter — the target only needs to adjoin owned
            # land (verified live). But an army mid-recruit/cure (pending drill/curing
            # pawns) can't be sent and poisons the whole occupy with ecode.500000, so
            # exclude those (they show no busy `state`, so check the pawn queues).
            from nta_agent.execution.army_health import is_idle
            # Armies the ArmyComposer is arranging are LOCKED — never send them to
            # occupy (would fight over pawns / rally). Composer takes priority.
            locked = set()
            if self.locked_source is not None:
                try:
                    locked = {str(u) for u in (self.locked_source() or ())}
                except Exception:
                    locked = set()
            avail = [a for a in actions.select_armies(i)
                     if is_idle(a) and not a.get("drillPawns") and not a.get("curingPawns")
                     and str(a.get("uid")) not in locked]
            grp = []
            if self.profile is not None:
                from nta_agent.execution.profile import active_formation
                grp = active_formation(self.profile).get("group") or []
            if grp:
                chosen = [a for a in avail if str(a.get("uid")) in {str(x) for x in grp}]
                avail = chosen or avail
            # Only combine CO-LOCATED armies: the sim models the engine's wave
            # schedule from per-army marchTime, but we feed marchTime=0, so it
            # assumes the same-origin schedule (lead at frame 0, others a frame+
            # later). That matches same-cell armies; scattered origins (different
            # distances) arrive on a schedule the sim can't see. See colocated_orders.
            # BRAIN policy: occupy.policy.order picks the lead army (tank_first /
            # dps_first) or lets the planner choose by loss (auto). Hands execute it.
            order_policy = "auto"
            if self.profile is not None:
                order_policy = (self.profile.occupy.get("policy") or {}).get("order") or "auto"
            # Inc 3: a lesson matching THIS cell's guardians overrides the order here
            # (a monster-specific lesson applies only when facing that monster).
            order_policy = self._recall_order(cand_by_index.get(i), order_policy)
            return [Plan(armies=order, target=i, label=label, prediction=None)
                    for label, order in colocated_orders(avail, order_policy)]

        def predict(plan):
            c = cand_by_index[plan.target]
            dist = self._dist(state.main_city_index, c.index)
            if sim is not None:
                try:
                    # Pass the REAL guardians (from get_area) as the enemy — letting the
                    # sim generate them from land_id fails here (get_area gives no
                    # land_id, so land_id=0 -> the generator throws -> SimUnavailable ->
                    # fell back to the pessimistic stats predictor).
                    enemy = None
                    if c.defenders:
                        enemy = {"armys": [{"index": c.index, "uid": "npc", "owner": "",
                                            "state": 2, "pawns": c.defenders}],
                                 "hp": [c.hp[0], c.hp[1]]}
                    pred = sim.predict_armies(
                        state, plan.armies, target_index=c.index, land_id=c.land_id,
                        distance=dist, enemy_army_conf=enemy)
                    pred.source = "sim"
                    return pred
                except SimUnavailable as e:
                    self._sim_fail = str(e)[:120]  # why the accurate sim was skipped
            pawns = [p for a in plan.armies for p in (a.get("pawns") or [])]
            pred = predictor.predict(pawns, c.defenders)
            pred.source = "stats"
            return pred

        # Selection priority: DEFENSE (claim a border cell an enemy is contesting)
        # > expansion preset > farming loot budget > plain safest-win.
        from nta_agent.execution import expansion as _exp
        mode = (self.profile.occupy.get("expansion") if self.profile else None) or "none"
        loot_on = (self.profile is not None
                   and (self.profile.occupy.get("loot") or {}).get("enabled", True))
        enemy = set(self.threats_source() or ()) if self.threats_source else set()
        plan = self._defensive_select(cands, plans_for, predict, enemy) if enemy else None
        if plan is not None:
            kind = "defend_border"
        elif mode in _exp.MODES:
            plan = self._expansion_select(cands, plans_for, predict, mode)
            kind = f"expansion:{mode}"
        elif loot_on:
            plan = self._farm_select(cands, plans_for, predict, state)
            kind = "farm_plan"
        else:
            plan = best_plan(cands, plans_for, predict, distance=self._plan_dist)
            kind = "occupy_plan"
        if plan is None:
            # No single/co-located force wins outright. If the FULL idle group,
            # once rallied together at the city, WOULD win a reachable target,
            # consolidate them there ("tập hợp trước") so a co-located attack can
            # follow next tick — instead of attacking scattered (which loses pawns
            # to staggered arrival). Only fires as a fallback, so it never
            # displaces a real single-army win.
            from nta_agent.execution.army_health import is_idle
            from nta_agent.execution.occupy_planner import plan_rally
            grp = set()
            if self.profile is not None:
                from nta_agent.execution.profile import active_formation
                grp = {str(x) for x in (active_formation(self.profile).get("group") or [])}
            try:
                allarmies = actions.get_player_armys()
            except Exception:
                allarmies = []
            idle_grp = [a for a in allarmies
                        if is_idle(a) and (a.get("pawns"))
                        and not a.get("drillPawns") and not a.get("curingPawns")
                        and (not grp or str(a.get("uid")) in grp)]
            max_loss = float(self.profile.occupy.get("max_loss", 0) or 0) if self.profile else 0.0

            # HEAL first: a wounded army that would clean-win its nearest target at
            # FULL hp but not now (wounds tip it from 0-loss to lossy), and is
            # convenient to a heal node (route passes near, or < 4 cells from the
            # city/a fort), is routed to heal — then attacks once recovered.
            hd = self._heal_diversion(cands, predict, idle_grp, state)
            if hd is not None:
                self._heal = hd
                self._pending = None
                if self.on_event:
                    w = 600
                    self.on_event("heal_divert", {
                        "army": hd[2], "to": hd[1], "to_xy": [hd[1] % w, hd[1] // w]})
                return True

            def _eval(armies, tgt):
                if tgt not in cand_by_index:
                    return None
                return predict(Plan(armies=armies, target=tgt, label="rally", prediction=None))
            ry = plan_rally(idle_grp, state.main_city_index, list(cand_by_index),
                            _eval, max_loss)
            if ry is not None:
                self._rally = (ry[0], state.main_city_index, ry[1])
                self._pending = None
                if self.on_event:
                    w = 600
                    self.on_event("rally", {
                        "to": state.main_city_index,
                        "armies": [a.get("name") or a.get("uid") for a in ry[0]],
                        "for_target": ry[1], "for_target_xy": [ry[1] % w, ry[1] // w]})
                return True
            return False
        self._rally = None
        self._heal = None
        self._pending = (list(plan.armies), plan.target)
        self._state_ref = state
        self._land_ref = cand_by_index[plan.target].land_id
        if self.on_event:
            pr = plan.prediction
            surv = pr.pawn_survival or []
            pred_deaths = sum(1 for s in surv
                              if s.get("camp") == 2 and not s.get("alive", True))
            self.on_event(kind, {
                "target": plan.target,
                "label": plan.label,
                "order": [a.get("name") or a.get("uid") for a in plan.armies],
                "loss_percent": round(pr.loss_percent, 1),
                # DIAGNOSTIC: which predictor decided this, its predicted deaths, and
                # (if the accurate engine sim was skipped) why it fell back to stats.
                "src": getattr(pr, "source", ""),
                "pred_deaths": pred_deaths,
                "sim_fail": self._sim_fail or None,
            })
        return True

    def _optimize_formations(self, actions, armies, target) -> None:
        """Reorder each melee army so the beefiest pawn tanks (fewest deaths, tie
        -> best damage spread), applied via ExchangePawnArmy swaps in the city.
        Best-effort: never block the occupy.

        Formation pawns (with hp/id, in list order) come from get_area(city);
        points are stripped before scoring so the sim decides by ORDER (pawns
        stack at the entry, just like a real battle)."""
        from nta_agent.execution.formation import candidate_orderings, swaps_for
        from nta_agent.execution.order_strategies import is_archer_army
        from nta_agent.execution.predictors.sim_bridge import SimUnavailable
        sim = self._sim_pred()
        if sim is None or self._state_ref is None:
            return
        city = self._state_ref.main_city_index
        dist = self._dist(city, target)
        try:
            area = actions.get_area(city).get("data", {})
        except Exception:
            return
        area_by_uid = {a.get("uid"): a for a in (area.get("armys") or [])}

        for army in armies:
            area_army = area_by_uid.get(army.get("uid"))
            if area_army is None:
                continue
            pawns = list(area_army.get("pawns") or [])
            if is_archer_army(area_army) or len(pawns) < 2:
                continue
            cands = candidate_orderings(area_army)
            if len(cands) < 2:
                continue

            au = army.get("uid")
            aidx = area_army.get("index", city)

            def _score(order, au=au, aidx=aidx):
                # strip points -> pawns stack at entry -> ORDER decides who tanks
                posed = {"uid": au, "index": aidx,
                         "pawns": [{k: v for k, v in p.items() if k != "point"} for p in order]}
                try:
                    pred = sim.predict_armies(self._state_ref, [posed], target_index=target,
                                              land_id=self._land_ref, distance=dist)
                except SimUnavailable:
                    return None
                if pred is None or not pred.win:
                    return None
                surv = pred.pawn_survival or []
                worst = max((100 - s.get("curHp", 0) for s in surv if s.get("camp") == 2), default=0)
                return (pred.loss_percent, worst)

            best = None
            for label, order in cands:
                sc = _score(order)
                if sc is None:
                    continue
                if best is None or sc < best[0]:
                    best = (sc, label, order)
            if best is None:
                continue
            sc, label, order = best
            cur_uids = [p.get("uid") for p in pawns]
            target_uids = [p.get("uid") for p in order]
            swaps = swaps_for(cur_uids, target_uids)
            if not swaps:
                continue
            try:
                for a_uid, b_uid in swaps:
                    actions.exchange_pawn_army(city, army["uid"], a_uid, b_uid)
                if self.on_event:
                    self.on_event("formation_plan", {
                        "army": army.get("name") or army.get("uid"),
                        "label": label, "loss_percent": round(sc[0], 1)})
            except Exception:
                pass  # never block the occupy

    def act(self, actions: Actions) -> None:
        if self._heal is not None:
            move, node, _name = self._heal
            self._heal = None
            # move the wounded army to the heal node (city/fort) to recover; it
            # attacks again once healed. Re-validate it's still idle with pawns.
            from nta_agent.execution.army_health import is_idle
            try:
                fresh = {str(a.get("uid")): a for a in actions.get_player_armys()}
            except Exception:
                fresh = {}
            cur = fresh.get(str(move.get("uid"))) if fresh else move
            if cur is not None and is_idle(cur) and (cur.get("pawns") or []):
                try:
                    actions.move_cell_army(
                        [{"uid": str(move["uid"]), "index": int(cur.get("index", 0) or 0)}], node)
                except Exception:
                    self._cooldown = self.fail_cooldown
            return
        if self._rally is not None:
            armies, city, _tgt = self._rally
            self._rally = None
            # One MoveCellArmy can pull armies from several cells home at once
            # (no battle, so staggered arrival is harmless). Re-validate to idle
            # armies that still have pawns, using their CURRENT index.
            from nta_agent.execution.army_health import is_idle
            try:
                fresh = {str(a.get("uid")): a for a in actions.get_player_armys()}
            except Exception:
                fresh = {}
            move = []
            for a in armies:
                cur = fresh.get(str(a.get("uid"))) if fresh else a
                if cur is not None and is_idle(cur) and (cur.get("pawns") or []):
                    move.append({"uid": str(cur.get("uid")),
                                 "index": int(cur.get("index", 0) or 0)})
            if move:
                try:
                    actions.move_cell_army(move, city)
                except Exception:
                    self._cooldown = self.fail_cooldown
            return
        if not self._pending:
            return
        armies, target = self._pending
        self._pending = None
        # Re-validate against fresh army state: between applies() and now, Logistics
        # (or a march/battle) may have emptied, moved or busied an army chosen from
        # the stale select_armys snapshot. Sending a stale/0-pawn army can make the
        # whole occupy fail (ecode.500000). Keep only armies that still exist, are
        # idle and have pawns, using their CURRENT index.
        from nta_agent.execution.army_health import is_idle
        try:
            fresh = {str(a.get("uid")): a for a in actions.get_player_armys()}
        except Exception:
            fresh = {}
        if fresh:
            valid = []
            for a in armies:
                cur = fresh.get(str(a.get("uid")))
                # skip armies that got emptied, moved-busy, or a pending drill/cure
                # between applies() and now — any of those makes the occupy 500000.
                if (cur is not None and is_idle(cur) and (cur.get("pawns") or [])
                        and not cur.get("drillPawns") and not cur.get("curingPawns")):
                    valid.append({"uid": str(cur.get("uid")), "index": int(cur.get("index", 0) or 0)})
            armies = valid
        if not armies:
            self._cooldown = self.fail_cooldown
            return
        # BRIDGING: to reach a FAR target (outside the speed zone), relay through
        # the in-zone owned cell nearest it — a fast in-zone march then a short
        # hop beats a long un-boosted direct march (engine isCanUpSpeed needs both
        # endpoints in-zone). Move there this tick and attack from it next tick.
        # Only fires for far targets; near targets attack directly. Forts extend
        # the zone, so late game this rarely triggers.
        if self.territory_source is not None and armies:
            try:
                owned, centers = self.territory_source()
            except Exception:
                owned, centers = set(), []
            launch = int(armies[0].get("index", 0) or 0)
            from nta_agent.execution.occupy_planner import bridge_hop
            hop = bridge_hop(launch, target, owned, centers) if centers else None
            if hop is not None and hop != launch:
                try:
                    actions.move_cell_army(
                        [{"uid": str(a["uid"]), "index": int(a.get("index", 0) or 0)}
                         for a in armies], hop)
                    if self.on_event:
                        w = 600
                        self.on_event("bridge", {
                            "stage": hop, "stage_xy": [hop % w, hop // w],
                            "target": target, "target_xy": [target % w, target // w]})
                    return  # relay launched; attack next tick from the staging cell
                except Exception as e:
                    # The relay cell can't take the armies (e.g. ecode.500037 — the
                    # staging area is already full of armies). Bridging is only a
                    # SPEED optimization; don't get stuck retrying it forever. Fall
                    # through to a direct (un-boosted) occupy so expansion advances.
                    if self.on_event:
                        ecode = str(e).split("ecode.")[-1][:6] if "ecode." in str(e) else ""
                        w = 600
                        self.on_event("bridge_skip", {
                            "ecode": ecode, "stage": hop, "stage_xy": [hop % w, hop // w],
                            "target": target, "target_xy": [target % w, target // w]})
        self._optimize_formations(actions, armies, target)
        try:
            actions.occupy_cell(target, armies)
        except Exception as e:
            self._cooldown = self.fail_cooldown
            ecode = str(e).split("ecode.")[-1][:6] if "ecode." in str(e) else ""
            # Benign duplicate/race — a march to this target already exists or an
            # army is already there (500080 armyIndex==target / not-owner; 500081
            # already enough armies marching there). Expansion is still happening;
            # just back off quietly instead of logging an error every time.
            if ecode in ("500080", "500081"):
                return
            if self.on_event:  # capture what we actually sent, to debug rejections
                w = 600
                self.on_event("occupy_error", {
                    "ecode": ecode,
                    "target": target, "target_xy": [target % w, target // w],
                    "land_id": self._land_ref,
                    "starts": [[int(a.get("index", 0)) % w, int(a.get("index", 0)) // w]
                               for a in armies],
                    "uids": [str(a.get("uid")) for a in armies]})
            raise


def _unused_army_name(armys) -> str:
    """A "D<k>" army name not already taken (count-based naming collides when an
    army is dismissed or named differently — the duplicate-name bug)."""
    existing = {str(a.get("name", "")) for a in (armys or [])}
    k = 1
    while f"D{k}" in existing:
        k += 1
    return f"D{k}"


@dataclass
class Recruit:
    """Recruit an already-unlocked pawn into an army at the main city.

    A pawn must be *unlocked* (present in player.pawnSlots) before it can be
    drilled — drilling a locked pawn returns ecode.500017. We recruit into a city
    army that has room (<9 pawns), or create a new one while under the army cap.
    Unlocking new pawn types (StudySelect) is a separate concern left to strategy.
    """
    name: str = "recruit"
    barracks_id: int = 2004
    max_army_pawns: int = 9
    max_armies: int = 4
    fail_cooldown: int = 10
    config: object = None
    profile: object = None    # Profile: fill armies toward army.composition
    locked_source: object = None  # callable -> army-uid set the ArmyComposer owns (skip them)
    _pending: object = None   # (build_uid, pawn_id, army_uid, army_name, pawn_count)
    _cooldown: int = 0
    # Armies the server rejected as full (ecode.500019), by uid -> pawn count when
    # rejected. The per-army cap is not in the data (it varies by army), so we learn
    # it: skip an army marked full until its pawn count changes.
    _full: dict = field(default_factory=dict)
    _max_army_count: int = 0   # learned army cap (ecode.500054); 0 = unknown
    _new_army_at: int = 0      # army count when the pending create was queued

    ARMY_FULL_ECODE = "ecode.500019"
    ARMY_COUNT_FULL_ECODE = "ecode.500054"  # PLAYER_FULL_ARMY: at getArmyMaxCount

    def _is_full(self, army: dict) -> bool:
        uid = str(army.get("uid"))
        if uid not in self._full:
            return False
        if self._full[uid] == len(army.get("pawns", [])):
            return True
        del self._full[uid]  # roster changed -> stale mark, re-evaluate
        return False

    def _cfg(self):
        if self.config is None:
            from nta_agent.data.config import GameConfig
            try:
                self.config = GameConfig.load()
            except FileNotFoundError:
                self.config = False
        return self.config or None

    def _unlocked_pawns(self, state: GameState) -> list[int]:
        slots = (state.raw or {}).get("player", {}).get("pawnSlots") or {}
        return [int(v["id"]) for v in slots.values() if isinstance(v, dict) and v.get("id")]

    def _affordable(self, state: GameState, pawn_id: int) -> bool:
        cfg = self._cfg()
        if not cfg:
            return True  # can't check -> let the server decide
        cost = cfg.pawn_recruit_cost(pawn_id)
        r = state.resources
        have = {"cereal": r.cereal, "timber": r.timber, "stone": r.stone, "iron": r.iron}
        return all(have.get(k, 0) >= v for k, v in cost.items())

    def applies(self, state: GameState, actions: Actions) -> bool:
        if self._cooldown > 0:
            self._cooldown -= 1
            return False
        bu = actions.building_uid(self.barracks_id)
        if not bu or not state.main_city_index:
            return False
        unlocked = self._unlocked_pawns(state)
        if not unlocked:
            return False  # nothing to recruit (needs StudySelect first)
        pawn = next((p for p in unlocked if self._affordable(state, p)), None)
        if pawn is None:
            return False
        armys = actions.get_area(state.main_city_index).get("data", {}).get("armys", []) or []
        # Skip armies the ArmyComposer is arranging (its lock): don't recruit into them
        # (it drives their composition) and don't compete for the drill queue on them.
        if self.locked_source is not None:
            try:
                locked = {str(u) for u in (self.locked_source() or ())}
            except Exception:
                locked = set()
            if locked:
                armys = [a for a in armys if str(a.get("uid")) not in locked]
        # profile-driven: fill the biggest composition gap into its own army.
        if self.profile is not None:
            from nta_agent.execution.profile import active_formation, composition_target
            comp = active_formation(self.profile).get("composition")
            tgt = composition_target(self.profile, armys, unlocked, composition=comp)
            if tgt is not None:
                army_uid, pid = tgt
                army = next((a for a in armys if str(a.get("uid")) == army_uid), None)
                if (army is not None and self._affordable(state, pid)
                        and not army.get("state")
                        and not self._is_full(army)
                        and len(army.get("pawns", [])) < self.max_army_pawns):
                    self._pending = (bu, pid, army_uid, "", len(army.get("pawns", [])))
                    return True
        # recruit into a non-marching city army that still has room
        room = next((a for a in armys
                     if not a.get("state") and not self._is_full(a)
                     and len(a.get("pawns", [])) < self.max_army_pawns), None)
        if room:
            self._pending = (bu, pawn, str(room["uid"]), "", len(room.get("pawns", [])))
        elif len(armys) < self.max_armies and not (
                self._max_army_count and len(armys) >= self._max_army_count):
            self._pending = (bu, pawn, "", _unused_army_name(armys), 0)
            self._new_army_at = len(armys)  # to learn the cap if the server rejects
        else:
            return False
        return True

    def act(self, actions: Actions) -> None:
        if not self._pending:
            return
        bu, pawn, au, name, count = self._pending
        self._pending = None
        try:
            actions.drill_pawn(bu, pawn, army_uid=au, army_name=name)
        except Exception as e:
            # "Army Soldier Full": our optimistic cap was wrong for this army.
            # Learn it and stop retrying this army — an expected condition, not an
            # error worth surfacing every cooldown.
            if au and self.ARMY_FULL_ECODE in str(e):
                self._full[str(au)] = count
                return
            # At the army cap (PLAYER_FULL_ARMY): stop trying to create new armies
            # until one is dismissed (army count drops below the learned cap).
            if not au and self.ARMY_COUNT_FULL_ECODE in str(e):
                self._max_army_count = self._new_army_at or 1
                return
            self._cooldown = self.fail_cooldown
            raise


@dataclass
class ClaimTreasures:
    """Open + claim treasures earned from occupying cells (deterministic).

    A pawn with a non-empty ``treasures`` field has a pending chest. We batch
    open (unopened) then claim, capped at the current chest budget. Best-effort:
    a batch error (e.g. already-opened) never blocks the loop.
    """
    name: str = "claim_treasures"
    _targets: object = None

    @staticmethod
    def _pending(armies) -> list[dict]:
        out = []
        for a in armies or []:
            if any((p.get("treasures") or []) for p in (a.get("pawns") or [])):
                out.append({"index": int(a.get("index", 0)), "auid": str(a.get("uid"))})
        return out

    def applies(self, state: GameState, actions: Actions) -> bool:
        # Cheap gate: only fetch armies when the server flags a new treasure.
        player = (state.raw or {}).get("player", {}) or {}
        if not player.get("hasNewTreasure"):
            return False
        try:
            armies = actions.get_player_armys()
        except Exception:
            return False
        from nta_agent.execution.treasure_model import chest_budget
        budget = chest_budget(state)
        targets = self._pending(armies)
        self._targets = targets[:budget] if budget < 10_000 else targets
        return bool(self._targets)

    def act(self, actions: Actions) -> None:
        targets, self._targets = self._targets, None
        if not targets:
            return
        try:
            actions.open_armys_treasure(targets)
            actions.claim_armys_treasure(targets)
        except Exception:
            pass  # best-effort; never block the loop


@dataclass
class ClaimTasks:
    """Claim completed task rewards (guide / other / today) — server-authoritative.

    Task ``progress`` isn't always maintained server-side (some conditions are
    verified only on claim), so instead of predicting completion we *attempt* the
    claim and let the server decide. A rejected id is backed off until the task
    lists change (progress advanced), then retried. Guide tasks in particular
    carry the early-game gameplay guidance + worthwhile rewards.
    """
    name: str = "claim_tasks"
    sweep_every: int = 20     # ticks between claim attempts (claiming isn't urgent)
    _seen: set = field(default_factory=set)   # (kind,id) already attempted this cycle
    _sig: tuple = ()          # task-list signature; changes reset _seen (retry as play advances)
    _cooldown: int = 0
    _pending: object = None    # (kind, id)

    _KINDS = (("guideTasks", "guide"), ("otherTasks", "other"), ("todayTasks", "today"))

    @staticmethod
    def _tasks(state: GameState, key: str) -> list[dict]:
        return (state.raw or {}).get("player", {}).get(key) or []

    def applies(self, state: GameState, actions: Actions) -> bool:
        if self._cooldown > 0:
            self._cooldown -= 1
            return False
        # When the task lists move (ids/progress changed, e.g. after a claim or as
        # play advances), forget what we tried so completed tasks get another go.
        sig = tuple(
            (kind, t.get("id"), t.get("progress"))
            for key, kind in self._KINDS for t in self._tasks(state, key)
        )
        if sig != self._sig:
            self._sig = sig
            self._seen.clear()
        for key, kind in self._KINDS:
            for t in self._tasks(state, key):
                tid = t.get("id")
                if tid is None or (kind, tid) in self._seen:
                    continue
                self._pending = (kind, tid)
                return True
        return False

    def act(self, actions: Actions) -> None:
        if not self._pending:
            return
        kind, tid = self._pending
        self._pending = None
        self._seen.add((kind, tid))  # attempted once per cycle, win or lose
        claim = {"guide": actions.claim_task,
                 "other": actions.claim_other_task,
                 "today": actions.claim_today_task}[kind]
        self._cooldown = self.sweep_every  # one claim per sweep
        try:
            claim(tid)
        except Exception:  # "not complete" is the expected case — stay quiet, retry next cycle
            return


@dataclass
class HealRouting:
    """Route wounded armies to the nearest fort/city to heal (passive server-side).

    Best-effort: keeps farming armies healthy so the occupy loop never stalls on
    weakened troops. Heal itself is automatic while an army sits at a fort/city;
    this rule only does the routing.
    """
    name: str = "heal_routing"
    fort_capacity: int = 5      # armies a heal node holds (maxArmyCount; refine live)
    check_every: int = 4        # ticks between get_player_armys() sweeps
    max_route_per_tick: int = 1
    on_event: object = None
    locked_source: object = None  # callable -> army-uid set the ArmyComposer owns (skip them)
    _cooldown: int = 0
    _pending: object = None

    def applies(self, state: GameState, actions: Actions) -> bool:
        if not state.main_city_index:
            return False
        if self._cooldown > 0:
            self._cooldown -= 1
            return False
        from nta_agent.execution.army_health import (
            army_is_wounded,
            army_wound_frac,
            is_idle,
            nearest_heal_node,
        )
        from nta_agent.execution.territory import build_territory
        armies = actions.get_player_armys()
        if self.locked_source is not None:  # don't route the composer's strike armies
            try:
                locked = {str(u) for u in (self.locked_source() or ())}
            except Exception:
                locked = set()
            if locked:
                armies = [a for a in armies if str(a.get("uid")) not in locked]
        self._cooldown = self.check_every
        terr = build_territory(state)
        nodes = {terr.main_city} | {f.index for f in terr.forts}
        occupancy: dict[int, int] = {}
        for a in armies:
            idx = int(a.get("index", 0) or 0)
            if idx in nodes:
                occupancy[idx] = occupancy.get(idx, 0) + 1
        # Only route IDLE wounded armies — a marching/fighting/recruiting/leveling
        # army can't be moved (server rejects: ecode.500020/500036/...).
        candidates = [a for a in armies
                      if army_is_wounded(a) and is_idle(a)
                      and int(a.get("index", 0) or 0) not in nodes]
        candidates.sort(key=army_wound_frac, reverse=True)
        pending = []
        for a in candidates[: self.max_route_per_tick]:
            node = nearest_heal_node(int(a["index"]), terr, occupancy, self.fort_capacity)
            if node is None:
                continue
            occupancy[node] = occupancy.get(node, 0) + 1  # reserve the slot
            pending.append((a, node))
        self._pending = pending
        if pending and self.on_event:
            self.on_event("heal_routing", {"count": len(pending),
                                           "armies": [a.get("uid") for a, _ in pending]})
        return bool(pending)

    def act(self, actions: Actions) -> None:
        for army, node in self._pending or []:
            actions.move_cell_army([army], node)
        self._pending = None


@dataclass
class ReviveInjured:
    """Revive dead pawns (``player.injuryPawns``) into a home army (deterministic).

    Best-effort, cost-aware: reviving spends resources + a curing-queue slot +
    time, and the slot/free-count limits are policy-driven (not fixed), so we
    cap per tick, keep a resource floor, and let the server enforce limits —
    backing off on rejection instead of hard-coding them.
    """
    name: str = "revive_injured"
    max_per_tick: int = 1
    capacity_hint: int = 9      # per-army pawn cap hint; server (500019) is truth
    min_cereal: int = 200       # resource floor: don't drain the economy reviving
    fail_cooldown: int = 8
    full_cooldown: int = 60     # no revive room (armies + army cap full) -> wait longer
    on_event: object = None
    profile: object = None
    _cooldown: int = 0
    _injured: object = None

    def _enabled(self) -> bool:
        if self.profile is None:
            return True
        rev = getattr(self.profile, "revive", None) or {}
        return bool(rev.get("enabled", True))

    def applies(self, state: GameState, actions: Actions) -> bool:
        if self._cooldown > 0:
            self._cooldown -= 1
            return False
        if not state.main_city_index or not self._enabled():
            return False
        if state.resources.cereal < self.min_cereal:
            return False
        player = (state.raw or {}).get("player") or {}
        self._injured = list(player.get("injuryPawns") or [])
        return bool(self._injured)

    def act(self, actions: Actions) -> None:
        from nta_agent.execution.injury import best_injured, revive_target
        main = actions.main_city_index()
        armies = actions.get_player_armys()
        for _ in range(self.max_per_tick):
            pawn = best_injured(self._injured)
            if pawn is None:
                break
            army_uid, army_name = revive_target(armies, main, self.capacity_hint)
            try:
                actions.cure_injury_pawn(main, army_uid, army_name, str(pawn.get("uid")))
            except Exception as e:
                self._cooldown = self.fail_cooldown  # full army / no slot / cost -> back off
                # Can't create a new army to revive into: the army cap is reached
                # (500054) or the area is army-full (500037). Every city army being
                # full made revive_target fall back to "create new", which then can't.
                # Expected until an army frees up — back off quietly, don't spam.
                if any(c in str(e) for c in ("ecode.500054", "ecode.500037")):
                    self._cooldown = self.full_cooldown
                    return
                raise
            self._injured = [p for p in self._injured
                             if str(p.get("uid")) != str(pawn.get("uid"))]
            if self.on_event:
                self.on_event("revive_injured", {"pawn": pawn.get("uid"),
                                                 "id": pawn.get("id"), "into": army_name or army_uid})
            armies = actions.get_player_armys()  # refresh occupancy for the next revive


@dataclass
class Leveling:
    """Run the exp-book leveling cycle over the FARM GROUP (profile.army.group,
    up to ~5 armies) + an agent-created LEVELING army (buffer). Best-effort.

    Inert until configured (enabled + target_lv). The agent pulls under-target
    pawns from the farm group into a new leveling army, levels them (PawnLving),
    and swaps ready pawns back into the farm group when it is home. Verified live:
    PawnLving costs exp_book + queues ~240s -> lv+1. (Create/dismiss army params
    to re-confirm live once a workable multi-army state exists.)"""
    name: str = "leveling"
    check_every: int = 4
    on_event: object = None
    profile: object = None
    _cooldown: int = 0
    _pending: object = None

    def _queue_uids(self, state) -> set:
        q = ((state.raw or {}).get("player") or {}).get("pawnLvingQueues")
        if isinstance(q, dict):
            uids = set(q.get("pawnUIDMap") or {})
            for item in (q.get("map") or {}).values():
                if isinstance(item, dict) and item.get("puid"):
                    uids.add(str(item["puid"]))
            return {str(u) for u in uids}
        return set()

    def applies(self, state: GameState, actions: Actions) -> bool:
        cfg = getattr(self.profile, "leveling", None) or {}
        if not cfg.get("enabled"):
            return False
        if self._cooldown > 0:
            self._cooldown -= 1
            return False
        target = int(cfg.get("target_lv", 0) or 0)
        if not target:
            return False
        from nta_agent.execution.leveling import find_leveling_army, next_level_action
        from nta_agent.execution.profile import active_formation
        group = {str(u) for u in (active_formation(self.profile).get("group") or [])}
        if not group:
            return False  # no fixed farm group designated
        armies = actions.get_player_armys()
        self._cooldown = self.check_every
        farm_armies = [a for a in armies if str(a.get("uid")) in group]
        level_army = find_leveling_army(armies)
        if not farm_armies:
            return False
        main = actions.main_city_index()
        # Only IDLE farm armies AT the city can have pawns pulled/swapped —
        # ChangePawnArmy/ExchangePawnArmy reject a marching or fighting army
        # (ecode.500020 "Đang hành quân"). Operate on those, and let leveling
        # proceed whenever at least ONE farm army is idle at home (not only when
        # ALL are) — the farm armies are usually out farming, so requiring all
        # home meant leveling never ran.
        from nta_agent.execution.army_health import is_idle
        home_farm = [a for a in farm_armies
                     if is_idle(a) and int(a.get("index", 0) or 0) == main]
        act = next_level_action(home_farm, level_army, target, farm_home=bool(home_farm),
                                queue_uids=self._queue_uids(state),
                                exp_book=state.resources.exp_book,
                                max_leveling=int(cfg.get("max_leveling", 1) or 1))
        self._pending = act
        if act and self.on_event:
            self.on_event("leveling", {"kind": act.kind,
                                       "pawn": act.pawn_uid or act.ready_uid})
        return act is not None

    fail_cooldown: int = 12
    quiet_cooldown: int = 24
    # Benign "already doing it / can't right now" ecodes: back off QUIETLY (no
    # error). 500079 = pawn already in the leveling queue (a PawnLving succeeded
    # but the queue/LVING state isn't synced into our snapshot yet — state
    # freshness, like the build queue); 500020 = the army started marching.
    # 500079 already-queued, 500020 army-marching, 500012 not-enough-resources
    # (exp-book ran out; a stale estimate let it try — wait, don't spam).
    QUIET_ECODES = ("500079", "500020", "500012")
    res_cooldown: int = 120    # ~10min: exp-books won't appear soon

    def act(self, actions: Actions) -> None:
        a = self._pending
        self._pending = None
        if a is None:
            return
        try:
            if a.kind == "level":
                actions.pawn_lving(a.index, a.level_uid, a.pawn_uid)
            elif a.kind == "swap":
                actions.exchange_pawn_army(a.index, a.farm_uid, a.low_uid, a.ready_uid,
                                           army_uid2=a.level_uid)
            elif a.kind == "pull":
                actions.change_pawn_army(a.index, a.src_uid, a.pawn_uid, a.level_uid,
                                         only_change=True)
            elif a.kind == "dismiss":
                actions.dismiss_army(a.index, a.level_uid, 0)
        except Exception as e:
            ecode = str(e).split("ecode.")[-1][:6] if "ecode." in str(e) else ""
            if ecode in self.QUIET_ECODES:
                # expected transient — already leveling / marching / out of books.
                # Out-of-resources waits longer (books are slow to arrive).
                self._cooldown = self.res_cooldown if ecode == "500012" else self.quiet_cooldown
                if ecode == "500012":
                    _record_res_block(self, "exp_book")
                return
            # a real rejection — back off and surface it instead of spamming.
            self._cooldown = self.fail_cooldown
            if self.on_event:
                self.on_event("leveling_error", {
                    "kind": a.kind, "ecode": ecode, "msg": str(e)[:80]})
            raise


@dataclass
class Logistics:
    """Consolidate under-strength field armies + bring them home to recruit, then
    let the brain redeploy the topped-up ones (profile.logistics.redeploy).

    Fills armies the way the player does when the pawn cap rises: pack high-hp
    pawns into a co-located keeper, march the short army home for ``Recruit`` to
    fill, and hand full+idle city armies to the brain. Opt-in (disabled by
    default); never touches fort/excluded armies. See
    docs/superpowers/specs/2026-09-19-army-logistics-design.md.
    """
    name: str = "logistics"
    check_every: int = 4
    fail_cooldown: int = 8
    profile: object = None
    on_event: object = None
    locked_source: object = None  # callable -> army-uid set the ArmyComposer owns (skip them)
    _cooldown: int = 0
    _pending: object = None   # ("plan", LogisticsAction) | ("redeploy", army, target)

    # ecodes that mean "this exact move can't happen now" — back off, don't spam.
    BUSY_ECODES = ("ecode.500019", "ecode.500036", "ecode.500037", "ecode.500020")

    def _cfg(self) -> dict | None:
        lg = getattr(self.profile, "logistics", None) if self.profile else None
        return lg if isinstance(lg, dict) and lg.get("enabled") else None

    def applies(self, state: GameState, actions: Actions) -> bool:
        if self._cooldown > 0:
            self._cooldown -= 1
            return False
        lg = self._cfg()
        if not lg or not state.main_city_index:
            return False
        from nta_agent.execution.logistics import plan_logistics, ready_armies
        from nta_agent.execution.territory import build_territory
        terr = build_territory(state)
        armies = actions.get_player_armys()
        # Never touch armies the ArmyComposer is arranging (its lock) — don't
        # consolidate or redeploy a strike army out from under the composer.
        if self.locked_source is not None:
            try:
                locked = {str(u) for u in (self.locked_source() or ())}
            except Exception:
                locked = set()
            if locked:
                armies = [a for a in armies if str(a.get("uid")) not in locked]
        self._cooldown = self.check_every
        main = terr.main_city
        # B: the brain assigned a topped-up army a destination -> send it out.
        redeploy = lg.get("redeploy") or {}
        if redeploy:
            ready = {str(a.get("uid")): a for a in ready_armies(
                armies, main, target=int(lg.get("target", 9)))}
            live = {str(a.get("uid")) for a in armies}
            for uid, target in list(redeploy.items()):
                uid, target = str(uid), int(target)
                if uid not in live:
                    redeploy.pop(uid, None)          # army gone -> drop stale order
                    continue
                army = ready.get(uid)
                if army is None:
                    continue                         # not full/idle yet -> wait
                if target == int(army.get("index", 0) or 0):
                    redeploy.pop(uid, None)          # already there -> drop no-op
                    continue
                self._pending = ("redeploy", army, target)
                return True
        # A: consolidate / bring under-strength field armies home.
        act = plan_logistics(armies, main, [f.index for f in terr.forts],
                             target=int(lg.get("target", 9)),
                             heal_skip_frac=float(lg.get("heal_skip_frac", 0.2)),
                             exclude=lg.get("exclude") or [],
                             min_shortfall=int(lg.get("min_shortfall", 1)))
        if act is None:
            return False
        self._pending = ("plan", act)
        if self.on_event:
            self.on_event("logistics", {"kind": act.kind, "index": act.index})
        return True

    def act(self, actions: Actions) -> None:
        pending, self._pending = self._pending, None
        if not pending:
            return
        try:
            if pending[0] == "redeploy":
                _, army, target = pending
                lg = self._cfg()
                if lg:  # consume BEFORE the call so a bad order never respams
                    (lg.get("redeploy") or {}).pop(str(army.get("uid")), None)
                actions.move_cell_army([army], target)
                return
            act = pending[1]
            if act.kind == "consolidate":
                for puid in act.pawn_uids:
                    actions.change_pawn_army(act.index, act.from_uid, puid,
                                             act.to_uid, only_change=True)
            elif act.kind == "bring_home":
                actions.move_cell_army([act.army], actions.main_city_index())
        except Exception as e:
            if any(code in str(e) for code in self.BUSY_ECODES):
                self._cooldown = self.fail_cooldown
                return
            self._cooldown = self.fail_cooldown
            raise


@dataclass
class Forge:
    """Craft (materialize) unlocked COMMON equipment so it can be equipped.

    A StudySelect-chosen equip sits in ``player.equipSlots`` as ``{id, lv}`` but is
    unusable until FORGED — forging uid ``"<id>_<lv>"`` (engine EquipSlotObj.uid)
    crafts it into ``player.equips``. We auto-craft common (non-pawn-locked) equips
    when their multi-resource forge cost is affordable; specialized equips + recast
    tuning stay the human's call. One forge at a time (server: ecode.500058).
    """
    name: str = "forge"
    fail_cooldown: int = 8
    forge_cooldown: int = 48   # ~4min: a forge takes time; don't poll it every tick
    res_cooldown: int = 120    # ~10min: not enough iron — wait, don't spam
    config: object = None
    profile: object = None
    on_event: object = None
    _cooldown: int = 0
    _pending: str = ""   # equip uid to forge

    FORGE_BUSY_ECODE = "ecode.500058"  # a forge is already running
    LOW_RES_ECODE = "ecode.500012"     # not enough resources (iron) yet

    def _cfg(self):
        if self.config is None:
            from nta_agent.data.config import GameConfig
            try:
                self.config = GameConfig.load()
            except FileNotFoundError:
                self.config = False
        return self.config or None

    def _enabled(self) -> bool:
        fg = getattr(self.profile, "forge", None) if self.profile else None
        return True if fg is None else bool(fg.get("enabled", True))

    def applies(self, state: GameState, actions: Actions) -> bool:
        if self._cooldown > 0:
            self._cooldown -= 1
            return False
        cfg = self._cfg()
        if not cfg or not self._enabled():
            return False
        player = (state.raw or {}).get("player") or {}
        if player.get("currForgeEquip"):
            return False  # a forge is already running
        from nta_agent.execution.forge import affordable, craft_candidates
        equips = player.get("equips") or []
        crafted = {int(e.get("id", 0) or 0) for e in equips if isinstance(e, dict)}
        cands = craft_candidates(
            player.get("equipSlots") or {},
            lambda i: cfg.table("equipBase").get(i),
            crafted, novice=(int(getattr(state, "room_type", 0) or 0) == 1))
        res = {"cereal": state.resources.cereal, "timber": state.resources.timber,
               "stone": state.resources.stone, "iron": state.resources.iron,
               "gold": state.resources.gold}
        for c in cands:
            if affordable(c["cost"], res):
                self._pending = c["uid"]
                if self.on_event:
                    self.on_event("forge", {"uid": c["uid"], "id": c["id"], "cost": c["cost"]})
                return True
        return False

    def act(self, actions: Actions) -> None:
        uid, self._pending = self._pending, ""
        if not uid:
            return
        try:
            actions.forge_equip(uid)
            # A forge takes time and its in-progress state isn't synced to us, so
            # wait it out instead of re-forging (which would hit ecode.500058).
            self._cooldown = self.forge_cooldown
        except Exception as e:
            # 500058 = a forge is already running (state didn't reflect it): expected,
            # back off quietly for the forge duration rather than surfacing an error.
            if self.FORGE_BUSY_ECODE in str(e):
                self._cooldown = self.forge_cooldown
                return
            if self.LOW_RES_ECODE in str(e):
                # not enough iron (a stale estimate let it try) — wait quietly.
                self._cooldown = self.res_cooldown
                _record_res_block(self, "iron")
                return
            self._cooldown = self.fail_cooldown
            raise


@dataclass
class ArmyComposer:
    """Reconcile armies toward the brain's strike-group target (army.strike_target),
    e.g. 1 army of rìu khiên (3206) + 4 armies of IMP (3305). Each tick it asks the
    pure planner for the next batch (rally scattered armies to the city, pull the right
    pawns from the pool, recruit the deficit) and applies it. It LOCKS the armies it is
    arranging (``locked_uids``) so occupy/logistics leave them alone, and persists the
    strike-army assignment across ticks. Reorg only pulls from non-reserved armies and
    never touches the farm group; heroes aren't fungible (handled in the planner).

    When the target is infeasible (a pawn type isn't unlocked, or it exceeds the army
    cap) it emits ``composition_blocked`` with the issues so the brain can tell the user.
    """
    name: str = "army_composer"
    barracks_id: int = 2004
    profile: object = None
    on_event: object = None          # on_event(kind, detail) -> surface to log/brain
    status_sink: object = None       # status_sink(dict) -> persist status for the brain advice loop
    fail_cooldown: int = 10
    res_cooldown: int = 60           # back off when short on resources / recruit queue (pacing)
    blocked_cooldown: int = 60
    _cooldown: int = 0
    _city: int = 0
    _strike_uids: list = field(default_factory=list)  # persisted assignment
    locked_uids: set = field(default_factory=set)     # armies occupy/logistics must skip
    _plan: object = None
    _blocked_notified: bool = False
    _done_notified: bool = False

    def _target(self):
        if self.profile is None:
            return None
        return list((getattr(self.profile, "army", None) or {}).get("strike_target") or [])

    @staticmethod
    def _unlocked(state) -> set:
        slots = (getattr(state, "raw", None) or {}).get("player", {}).get("pawnSlots") or {}
        return {int(v["id"]) for v in slots.values() if isinstance(v, dict) and v.get("id")}

    def _reserved(self, state) -> set:
        if self.profile is None:
            return set()
        from nta_agent.execution.profile import active_formation
        return {str(u) for u in (active_formation(self.profile).get("group") or [])}

    def applies(self, state: GameState, actions: Actions) -> bool:
        if self._cooldown > 0:
            self._cooldown -= 1
            return False
        target = self._target()
        if not target:  # no goal -> release any lock and stand down
            self.locked_uids = set()
            self._strike_uids = []
            self._status({"active": False})
            return False
        city = int(getattr(state, "main_city_index", 0) or 0)
        if not city:
            return False
        try:
            armies = actions.get_player_armys() or []
        except Exception:
            return False
        from nta_agent.execution.composition_plan import plan_composition_step
        plan = plan_composition_step(target, armies, city, self._strike_uids,
                                     self._reserved(state), self._unlocked(state), army_cap=0)
        self._plan = plan
        self._city = city
        self._strike_uids = [a["uid"] for a in plan["assign"]]
        # Lock only the strike armies still being ASSEMBLED (short of target). A
        # completed one is released so occupy can send it farming — it earns loot
        # (funding the remaining recruits) and stays intact at max_loss=0; the group
        # regroups later. (User: "đội mộ xong đi farm, đội còn lại mộ tiếp rồi hội quân".)
        by_uid = {str(a.get("uid")): a for a in armies}
        incomplete = set()
        for a in plan["assign"]:
            u = a["uid"]
            army = by_uid.get(u) if u else None
            have = sum(1 for p in (army.get("pawns") or [])
                       if int(p.get("id", 0) or 0) == a["pawn_id"]) if army else 0
            if u and have < a["size"]:
                incomplete.add(u)
        self.locked_uids = incomplete
        issues = list(plan["report"].issues)
        if plan["blocked"]:
            self._status({"active": True, "blocked": True, "done": False,
                          "issues": issues, "strike": self._strike_uids})
            if self.on_event and not self._blocked_notified:
                self.on_event("composition_blocked", {"issues": issues})
                self._blocked_notified = True
            self._cooldown = self.blocked_cooldown
            return False
        self._blocked_notified = False
        if plan["done"]:
            self._status({"active": True, "blocked": False, "done": True,
                          "issues": issues, "strike": self._strike_uids})
            if self.on_event and not self._done_notified:
                self.on_event("composition_done", {"strike": self._strike_uids})
                self._done_notified = True
            return False
        self._done_notified = False
        self._status({"active": True, "blocked": False, "done": False,
                      "issues": issues, "strike": self._strike_uids})
        return bool(plan["actions"])

    def _status(self, s: dict) -> None:
        if self.status_sink is not None:
            try:
                self.status_sink(s)
            except Exception:
                pass

    def act(self, actions: Actions) -> None:
        plan = self._plan
        self._plan = None
        if not plan:
            return
        try:
            armies = {str(a.get("uid")): a for a in (actions.get_player_armys() or [])}
        except Exception:
            armies = {}
        city = self._city
        for a in plan["actions"]:
            op = a["op"]
            try:
                if op == "rally":
                    mv = [{"uid": u, "index": int(armies.get(u, {}).get("index", city) or city)}
                          for u in a["uids"] if u in armies]
                    if mv:
                        actions.move_cell_army(mv, a["to"])
                elif op == "move_pawn":
                    actions.change_pawn_army(city, a["from"], a["pawn"], a["to"])
                elif op == "dismiss_pawn":
                    actions.dismiss_pawn(city, a["army"], a["pawn"])
                elif op == "recruit":
                    bu = actions.building_uid(self.barracks_id)
                    if bu:  # drill ONE pawn/tick into the short army; the queue paces the rest
                        actions.drill_pawn(bu, a["pawn_id"], army_uid=a.get("army") or "")
            except Exception as e:
                ecode = str(e).split("ecode.")[-1][:6] if "ecode." in str(e) else ""
                # Not enough resources (500012) / recruit-queue full (500018): can't make
                # progress this tick — back off quietly for a while (recruiting the group
                # is resource-paced) instead of hammering the API every tick.
                if ecode in ("500012", "500018"):
                    self._cooldown = self.res_cooldown
                    if ecode == "500012":
                        _record_res_block(self, "cereal")  # recruit is cereal-paced
                    return
                # Other expected mid-reorg conditions — skip THIS action, continue the
                # batch (a benign failure must not abort the tick / block the recruit):
                # army full/busy/not-found, army-cap, duplicate-march (500080/81).
                if ecode in ("500019", "500020", "500011", "500017", "500054",
                             "500080", "500081"):
                    continue
                # unexpected -> surface once and stop this tick's batch, back off.
                self._cooldown = self.fail_cooldown
                if self.on_event:
                    self.on_event("composition_error", {"op": op, "ecode": ecode})
                return


@dataclass
class RuleEngine:
    rules: list[Rule]
    on_error: object = None  # optional on_error(rule_name, exc): full error sink (ErrorLog)

    def tick(self, state: GameState, actions: Actions) -> list[str]:
        """Run every applicable rule once; return the names that fired."""
        fired: list[str] = []
        for rule in self.rules:
            try:
                if rule.applies(state, actions):
                    rule.act(actions)
                    fired.append(rule.name)
            except CaptchaRequired:
                raise
            except Exception as e:  # a failing rule must not kill the loop
                if ANTI_CHEAT_ECODE in str(e):
                    raise CaptchaRequired(str(e)) from e
                from nta_agent.io.api.client import is_session_error
                if is_session_error(e):
                    raise  # session down -> let the agent loop reconnect, don't swallow
                detail = str(e).split(":")[-1].strip() or type(e).__name__
                fired.append(f"{rule.name}!ERR:{detail}")
                if self.on_error is not None:
                    try:
                        self.on_error(rule.name, e)
                    except Exception:
                        pass  # error logging must never break the loop
        return fired

    @classmethod
    def default(cls, profile: object = None) -> RuleEngine:
        return cls(rules=[CollectCityOutput(), BuildOrder(profile=profile),
                          Recruit(profile=profile),
                          ArmyComposer(profile=profile),
                          HealRouting(),
                          OccupyCell(use_sim=True, profile=profile, radius=4),
                          ClaimTreasures(), ReviveInjured(profile=profile),
                          Leveling(profile=profile), Forge(profile=profile),
                          Logistics(profile=profile), ClaimTasks()])
