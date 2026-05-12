"""Detection state passed between requests (module design v1 §3.6)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Mapping

from .enums import QueuedTriggerKind


def _empty_map() -> Mapping[str, datetime]:
    return MappingProxyType({})


def _empty_retrigger_map() -> Mapping[str, "RetriggerEntry"]:
    return MappingProxyType({})


def _empty_watch_map() -> Mapping[str, "ArcWatchState"]:
    return MappingProxyType({})


@dataclass(frozen=True)
class RetriggerEntry:
    count: int = 0
    quiet_cycles: int = 0
    last_fired_at: datetime | None = None


@dataclass(frozen=True)
class QueuedTrigger:
    kind: QueuedTriggerKind
    first_fired_at: datetime
    last_fired_at: datetime
    accumulated_score: float
    snapshot_ref: str
    origin_edge_id: str | None = None
    origin_node_id: str | None = None


@dataclass(frozen=True)
class ArcWatchState:
    edge_id: str
    percentile_satisfied: bool
    delta_satisfied: bool
    started_at: datetime | None = None


@dataclass(frozen=True)
class DetectionState:
    cooldown_until: datetime | None = None
    warmup_until_by_target: Mapping[str, datetime] = field(default_factory=_empty_map)
    trigger_queue: tuple[QueuedTrigger, ...] = ()
    arc_watch_states: Mapping[str, ArcWatchState] = field(default_factory=_empty_watch_map)
    arc_retrigger_counts: Mapping[str, RetriggerEntry] = field(default_factory=_empty_retrigger_map)
    consecutive_skip_count: int = 0


def freeze_map(d: Mapping[str, datetime]) -> Mapping[str, datetime]:
    """Return an immutable view of a mapping (for safety in DetectionState fields)."""
    return MappingProxyType(dict(d))


def freeze_watch_map(d: Mapping[str, ArcWatchState]) -> Mapping[str, ArcWatchState]:
    return MappingProxyType(dict(d))


def freeze_retrigger_map(d: Mapping[str, RetriggerEntry]) -> Mapping[str, RetriggerEntry]:
    return MappingProxyType(dict(d))
