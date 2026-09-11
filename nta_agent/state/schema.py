"""Normalized GameState — the single model every layer reads and writes.

Both adapters feed this: the API adapter (authoritative, from S2C messages and
the tutorial ``novice_data`` snapshot) and, later, the vision adapter. The hands
(rules/predictors) and the brain (LLM) only ever read ``GameState``; they never
touch adapters directly.

Design: a typed *core* for the fields the agent actually reasons about, plus a
``raw`` dict escape hatch so nothing from the source is ever lost. Fields we have
not modelled yet still round-trip through ``raw`` and can be promoted later.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Resources:
    """Primary + special resources. Names mirror the game's own keys."""
    cereal: int = 0   # food / lương
    timber: int = 0   # wood / gỗ
    stone: int = 0    # đá
    iron: int = 0     # sắt
    gold: int = 0     # premium currency / vàng
    stamina: int = 0
    exp_book: int = 0
    up_scroll: int = 0
    fixator: int = 0


@dataclass
class Building:
    index: int              # the area/tile index this build sits on
    id: int                 # building type id
    lv: int                 # level
    uid: str = ""           # server-unique instance id
    point: tuple[int, int] = (0, 0)  # (x, y) within the area grid


@dataclass
class Area:
    """A map tile/area the player owns or is interacting with."""
    index: int
    owner: str = ""
    city_id: int = 0
    land_id: int = 0
    hp: tuple[int, int] = (0, 0)  # (current, max)
    buildings: list[Building] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class March:
    """An army movement (attack/collect/return). Loosely typed until observed live."""
    uid: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Slot:
    """A generic unlockable slot (pawn/policy/equip): level-gated, may hold an id."""
    slot: int
    lv: int = 0
    id: int = 0


@dataclass
class Hero:
    lv: int = 0
    avatar_army_uid: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class User:
    uid: str = ""
    nickname: str = ""
    login_type: str = ""
    session_id: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class GameState:
    user: User = field(default_factory=User)
    resources: Resources = field(default_factory=Resources)
    areas: dict[int, Area] = field(default_factory=dict)
    builds: list[Building] = field(default_factory=list)  # the player's own buildings (live)
    marches: list[March] = field(default_factory=list)
    pawn_slots: list[Slot] = field(default_factory=list)
    policy_slots: list[Slot] = field(default_factory=list)
    equip_slots: list[Slot] = field(default_factory=list)
    heroes: list[Hero] = field(default_factory=list)
    chapter: int = 0
    land_score: int = 0
    main_city_index: int = 0  # area index of the main city (target for its builds)
    build_queue: list[dict] = field(default_factory=list)  # in-progress upgrades (btQueues)
    build_queue_slots: int = 1  # how many concurrent builds are allowed

    # economy: production rate per resource (per hour) and storage caps
    production: dict[str, int] = field(default_factory=dict)
    granary_cap: int = 0    # cereal storage
    warehouse_cap: int = 0  # timber/stone storage

    # provenance
    source: str = ""          # "novice" | "api" | "vision"
    updated_at: float = field(default_factory=time.time)
    # everything from the source that isn't promoted to a typed field yet
    raw: dict[str, Any] = field(default_factory=dict)

    # ---- convenience ----------------------------------------------------- #
    @property
    def main_city(self) -> Area | None:
        """The area holding the player's main city.

        A positive ``city_id`` marks a real city tile (negatives are ruins/other),
        so pick the owned one with the highest positive id. Falls back to any
        positive-id area (the tutorial world assigns NPC owners).
        """
        cities = [a for a in self.areas.values() if a.city_id > 0]
        if not cities:
            return None
        owned = [a for a in cities if a.owner == self.user.uid]
        pool = owned or cities
        return max(pool, key=lambda a: a.city_id)

    def buildings(self) -> list[Building]:
        return [b for a in self.areas.values() for b in a.buildings]
