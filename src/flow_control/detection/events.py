"""Event application logic for the Detection step.

Module design v1 §4.3 step 2 and §4.6.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Iterable

from ..models import (
    ArcWatchState,
    DetectionState,
    Event,
    EventKind,
    Graph,
    QueuedTrigger,
    QueuedTriggerKind,
    ResolvedConfig,
    RetriggerEntry,
    TriggerEvidence,
    TriggerSource,
    freeze_map,
    freeze_retrigger_map,
    freeze_watch_map,
    make_edge_key,
    make_node_key,
)


def _is_edge_event(event: Event, graph: Graph) -> bool:
    return graph.edge_by_id(event.target_id) is not None


def _is_node_event(event: Event, graph: Graph) -> bool:
    return graph.node_by_id(event.target_id) is not None


def apply_events(
    state: DetectionState,
    events: Iterable[Event],
    graph: Graph,
    config: ResolvedConfig,
    server_time: datetime,
) -> tuple[DetectionState, list[QueuedTrigger], list[TriggerEvidence]]:
    """Apply events to ``state`` and emit any danger triggers.

    Returns the updated detection state, the list of danger triggers produced
    by ``DANGER_FLAG_UP`` events, and matching trigger evidences. The returned
    state is a new immutable value; the input is not mutated.
    """
    warmup_until = dict(state.warmup_until_by_target)
    retrigger_counts = dict(state.arc_retrigger_counts)
    watch_states = dict(state.arc_watch_states)
    cooldown_until = state.cooldown_until

    danger_triggers: list[QueuedTrigger] = []
    danger_evidences: list[TriggerEvidence] = []
    warmup_duration = timedelta(minutes=config.warmup_duration_min)

    for event in events:
        kind = event.kind
        if kind is EventKind.DANGER_FLAG_UP:
            edge_id: str | None = None
            node_id: str | None = None
            if _is_edge_event(event, graph):
                edge_id = event.target_id
            elif _is_node_event(event, graph):
                node_id = event.target_id
            else:
                edge_id = event.target_id
            danger_triggers.append(
                QueuedTrigger(
                    kind=QueuedTriggerKind.DANGER,
                    first_fired_at=event.occurred_at,
                    last_fired_at=event.occurred_at,
                    accumulated_score=1.0,
                    snapshot_ref=event.occurred_at.isoformat(),
                    origin_edge_id=edge_id,
                    origin_node_id=node_id,
                )
            )
            danger_evidences.append(
                TriggerEvidence(
                    source=TriggerSource.DANGER,
                    occurred_at=event.occurred_at,
                    edge_id=edge_id,
                    node_id=node_id,
                )
            )
        elif kind is EventKind.DANGER_FLAG_DOWN:
            retrigger_counts.pop(event.target_id, None)
            watch_states.pop(event.target_id, None)
        elif kind in (EventKind.SCHEDULED_INFLOW, EventKind.SCHEDULED_ATTR_CHANGE):
            cooldown_until = None
        elif kind in (EventKind.ENABLE, EventKind.ADD_NODE, EventKind.ADD_EDGE):
            if kind is EventKind.ADD_NODE:
                key = make_node_key(event.target_id)
            elif kind is EventKind.ADD_EDGE:
                key = make_edge_key(event.target_id)
            else:
                if _is_node_event(event, graph):
                    key = make_node_key(event.target_id)
                elif _is_edge_event(event, graph):
                    key = make_edge_key(event.target_id)
                else:
                    key = make_edge_key(event.target_id)
            warmup_until[key] = event.occurred_at + warmup_duration
        elif kind is EventKind.DISABLE:
            edge_key = make_edge_key(event.target_id)
            node_key = make_node_key(event.target_id)
            warmup_until.pop(edge_key, None)
            warmup_until.pop(node_key, None)
            retrigger_counts.pop(event.target_id, None)
            watch_states.pop(event.target_id, None)
        elif kind is EventKind.DIRECTION_SWITCH:
            # 直接 graph に反映済みの前提（要件 v1 §3.7 / §8）。
            # クールタイムも検知状態も触らない。
            pass
        else:
            # 未知 kind は無視（前方互換）
            pass

    new_state = replace(
        state,
        cooldown_until=cooldown_until,
        warmup_until_by_target=freeze_map(warmup_until),
        arc_retrigger_counts=freeze_retrigger_map(_filter_retrigger(retrigger_counts)),
        arc_watch_states=freeze_watch_map(_filter_watch_states(watch_states)),
    )
    return new_state, danger_triggers, danger_evidences


def _filter_retrigger(d: dict[str, RetriggerEntry]) -> dict[str, RetriggerEntry]:
    return {k: v for k, v in d.items() if isinstance(v, RetriggerEntry)}


def _filter_watch_states(d: dict[str, ArcWatchState]) -> dict[str, ArcWatchState]:
    return {k: v for k, v in d.items() if isinstance(v, ArcWatchState)}
