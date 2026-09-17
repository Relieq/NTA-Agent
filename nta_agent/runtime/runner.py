"""Wire config + bootstrap + session + Agent into a runnable, observable spine."""
from __future__ import annotations

import sys

from nta_agent.data.config import GameConfig
from nta_agent.execution.agent import Agent
from nta_agent.execution.captcha import CaptchaSolver
from nta_agent.execution.heuristics import RuleEngine
from nta_agent.io.adb import DeviceManager
from nta_agent.io.api.client import ServerConfig
from nta_agent.io.api.session import GameSession
from nta_agent.io.bootstrap import make_token_refresher
from nta_agent.runtime.config import RuntimeConfig
from nta_agent.runtime.control import read_mode
from nta_agent.runtime.decision_service import DecisionService
from nta_agent.runtime.eventlog import EventLog
from nta_agent.runtime.snapshot import write_snapshot


def run_services(state, cfg, service, brain, forts, safe) -> bool:
    """Run the acting services unless paused. Returns True if it acted."""
    if read_mode(cfg.control_path) == "pause":
        return False  # observe only while paused
    if service is not None:
        safe(service.tick, state)
    safe(brain.tick, state)
    safe(forts.tick, state)
    return True


def build_session(cfg: RuntimeConfig) -> GameSession:
    dm = DeviceManager.connect()
    refresher = make_token_refresher(dm, cfg.token_path)
    session = GameSession(server=ServerConfig(host=cfg.host),
                          token_path=cfg.token_path, token_refresher=refresher)
    session.connect(timeout=15)
    session.login(distinct_id=cfg.distinct_id)
    session.enter_game(distinct_id=cfg.distinct_id)
    return session


def run(cfg: RuntimeConfig, *, ticks: int = 0, session=None, engine=None) -> None:
    log = EventLog(cfg.event_log_path)
    if session is None:
        session = build_session(cfg)
        log.append("started", {"host": cfg.host})
    from nta_agent.execution.profile import load_profile
    profile = load_profile(cfg.profile_path)  # shared by the rules and the brain
    if engine is None:
        engine = RuleEngine.default(profile=profile)
    agent = Agent(session, engine, max_backoff=cfg.max_backoff, on_event=log.append)

    try:
        config = GameConfig.load()
    except FileNotFoundError:
        config = None
        log.append("config_missing")
    service = None
    if config is not None:
        service = DecisionService(agent.actions, config, cfg, on_event=log.append,
                                  profile=profile)
        agent.captcha = CaptchaSolver(agent.actions, config)
    from nta_agent.runtime.brain_service import BrainService
    brain = BrainService(profile, cfg, on_event=log.append, actions=agent.actions)
    from nta_agent.runtime.fort_service import FortService
    forts = FortService(cfg, agent.actions, on_event=log.append)
    # Surface the occupy planner's reasoning (chosen army + predicted loss) to the log.
    for rule in getattr(agent.engine, "rules", []):
        if getattr(rule, "name", "") == "occupy_cell":
            rule.on_event = log.append

    def _safe(fn, *a):
        try:
            fn(*a)
        except Exception as e:  # observability must not kill the loop
            sys.stderr.write(f"[spine] {fn.__name__} failed: {e}\n")

    def on_tick(i, fired, state):
        _safe(write_snapshot, state, cfg.snapshot_path)
        _safe(log.tick, i, fired, state)
        run_services(state, cfg, service, brain, forts, _safe)

    try:
        agent.run(ticks=ticks, interval=cfg.interval, on_tick=on_tick,
                  control=lambda: read_mode(cfg.control_path))
    except KeyboardInterrupt:
        log.append("interrupted")
    finally:
        _safe(write_snapshot, session.state, cfg.snapshot_path)
        session.close()
