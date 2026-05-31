from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from ..domain.graph import EdgeID, NodeID


class QueuedTriggerKind(str, Enum):
    SURGE = "SURGE"  # 急増
    HIGH_STAGNATION = "HIGH_STAGNATION"  # 高停滞
    DANGER = "DANGER"  # 危険フラグ


@dataclass(frozen=True)
class QueuedTrigger:
    kind: QueuedTriggerKind
    first_fired_at: datetime
    last_fired_at: datetime
    accumulated_score: float = 0.0
    origin_edge_id: EdgeID | None = None
    origin_node_id: NodeID | None = None


@dataclass(frozen=True)
class ArcWatchState:
    edge_id: EdgeID
    percentile_breached: bool = False
    delta_breached: bool = False
    started_at: datetime | None = None


@dataclass(frozen=True)
class WarmupState:
    target_key: str  # "edge:<id>" / "node:<id>"
    until: datetime


@dataclass(frozen=True)
class DetectionState:
    cooldown_until: datetime | None = None
    trigger_queue: tuple[QueuedTrigger, ...] = ()
    arc_watch_states: tuple[ArcWatchState, ...] = ()
    warmup_states: tuple[WarmupState, ...] = ()

    def watch_state_of(self, edge_id: EdgeID) -> ArcWatchState | None:
        for watch in self.arc_watch_states:
            if watch.edge_id == edge_id:
                return watch
        return None

    def is_in_cooldown(self, server_time: datetime) -> bool:
        return self.cooldown_until is not None and server_time < self.cooldown_until

    def warmup_until_of(self, target_key: str) -> datetime | None:
        for warmup in self.warmup_states:
            if warmup.target_key == target_key:
                return warmup.until
        return None

    def is_in_warmup(self, target_key: str, server_time: datetime) -> bool:
        until = self.warmup_until_of(target_key)
        return until is not None and server_time < until
