from dataclasses import dataclass
from datetime import datetime

from ..domain.graph import EdgeID, Graph, NodeID
from .config import ResolvedConfig
from .history import HistoryDigest
from .observations import Observations
from .state import DetectionState, QueuedTriggerKind
from .triggers import (
    Event,
    FiredTrigger,
    VerdictHint,
    detect_manual_triggers,
    detect_metric_triggers,
    evaluate_cooldown,
)


@dataclass(frozen=True)
class DetectionResult:
    verdict_hint: VerdictHint
    triggered_edges: tuple[EdgeID, ...]
    triggered_nodes: tuple[NodeID, ...]
    effective_snapshot: Observations
    new_state: DetectionState


def detect(
    graph: Graph,
    observations: Observations,
    history_digest: HistoryDigest,
    previous_state: DetectionState,
    events: tuple[Event, ...],
    config: ResolvedConfig,
    server_time: datetime,
) -> DetectionResult:
    metric_result = detect_metric_triggers(
        graph=graph,
        observations=observations,
        history_digest=history_digest,
        previous_state=previous_state,
        server_time=server_time,
        config=config,
    )

    manual_result = detect_manual_triggers(events=events)
    danger_triggers = tuple(
        FiredTrigger(
            kind=QueuedTriggerKind.DANGER,
            fired_at=server_time,
            origin_edge_id=edge_id,
        )
        for edge_id in manual_result.triggered_edges
    ) + tuple(
        FiredTrigger(
            kind=QueuedTriggerKind.DANGER,
            fired_at=server_time,
            origin_node_id=node_id,
        )
        for node_id in manual_result.triggered_nodes
    )

    decision = evaluate_cooldown(
        previous_state=metric_result.new_state,
        fired_triggers=danger_triggers + metric_result.fired_triggers,
        server_time=server_time,
        config=config,
    )

    return DetectionResult(
        verdict_hint=decision.verdict,
        triggered_edges=decision.triggered_edges,
        triggered_nodes=decision.triggered_nodes,
        effective_snapshot=observations,
        new_state=decision.new_state,
    )
