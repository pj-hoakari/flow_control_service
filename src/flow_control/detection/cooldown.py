"""Cooldown / queue handling.

Module design v1 §4.3 step 4 / math companion v1 §9.4.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Iterable

from ..models import (
    DetectionState,
    Observations,
    QueuedTrigger,
    ResolvedConfig,
)


def in_cooldown(state: DetectionState, server_time: datetime) -> bool:
    return state.cooldown_until is not None and server_time < state.cooldown_until


def queue_push(
    state: DetectionState,
    new_triggers: Iterable[QueuedTrigger],
    observations: Observations,
    server_time: datetime,
) -> DetectionState:
    """Merge ``new_triggers`` into ``state.trigger_queue`` (immutable).

    Same ``(kind, origin_edge_id)`` entries are merged by adding their
    ``accumulated_score``; ``last_fired_at`` is updated to ``server_time``.
    """
    queue = list(state.trigger_queue)

    for trig in new_triggers:
        merged = False
        for idx, existing in enumerate(queue):
            if existing.kind is trig.kind and existing.origin_edge_id == trig.origin_edge_id:
                queue[idx] = QueuedTrigger(
                    kind=existing.kind,
                    first_fired_at=existing.first_fired_at,
                    last_fired_at=server_time,
                    accumulated_score=existing.accumulated_score + trig.accumulated_score,
                    snapshot_ref=observations.observed_at.isoformat(),
                    origin_edge_id=existing.origin_edge_id,
                    origin_node_id=existing.origin_node_id,
                )
                merged = True
                break
        if not merged:
            queue.append(
                replace(
                    trig,
                    last_fired_at=server_time,
                    snapshot_ref=observations.observed_at.isoformat(),
                )
            )

    return replace(state, trigger_queue=tuple(queue))


def queue_exceeds_score(state: DetectionState, config: ResolvedConfig) -> bool:
    total = sum(q.accumulated_score for q in state.trigger_queue)
    return total > config.queue_score_threshold


def queue_is_diverse(state: DetectionState, config: ResolvedConfig) -> bool:
    edges = {q.origin_edge_id for q in state.trigger_queue if q.origin_edge_id is not None}
    return len(edges) > config.queue_diversity_threshold


def clear_queue(state: DetectionState) -> DetectionState:
    return replace(state, trigger_queue=())
