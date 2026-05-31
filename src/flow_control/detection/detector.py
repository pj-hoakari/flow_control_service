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
    all_targets_in_warmup,
    apply_warmup_events,
    detect_manual_triggers,
    detect_metric_triggers,
    evaluate_cooldown,
    has_danger_event,
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
    # イベント適用: ENABLE/ADD_* で対象別ウォームアップを設定
    state = apply_warmup_events(previous_state, events, server_time, config)

    # 全対象がウォームアップ中かつ危険フラグなしなら検知をスキップ
    if all_targets_in_warmup(state, graph, server_time) and not has_danger_event(
        events
    ):
        return DetectionResult(
            verdict_hint=VerdictHint.SKIPPED_WARMUP,
            triggered_edges=(),
            triggered_nodes=(),
            effective_snapshot=observations,
            new_state=state,
        )

    metric_result = detect_metric_triggers(
        graph=graph,
        observations=observations,
        history_digest=history_digest,
        previous_state=state,
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
