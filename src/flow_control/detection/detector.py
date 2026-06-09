from dataclasses import dataclass, replace
from datetime import datetime

from ..domain.graph import EdgeID, Graph, NodeID
from ..domain.history import HistoryDigest
from ..domain.observations import Observations
from .config import ResolvedConfig
from .diagnostics import DangerEvidence, TriggerEvidence
from .state import DetectionState, QueuedTriggerKind
from .triggers import (
    Event,
    FiredTrigger,
    VerdictHint,
    all_targets_in_warmup,
    apply_danger_flag_down,
    apply_scheduled_events,
    apply_warmup_events,
    detect_manual_triggers,
    detect_metric_triggers,
    evaluate_cooldown,
    has_danger_event,
    update_retrigger_counts,
)


@dataclass(frozen=True)
class DetectionResult:
    verdict_hint: VerdictHint
    triggered_edges: tuple[EdgeID, ...]
    triggered_nodes: tuple[NodeID, ...]
    effective_snapshot: Observations
    new_state: DetectionState
    evidences: tuple[TriggerEvidence, ...] = ()


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
    # イベント適用: SCHEDULED_* でクールタイムをリセット（キューは保持）
    state = apply_scheduled_events(state, events)
    # イベント適用: DANGER_FLAG_DOWN で当該アークの既存再発火カウントをリセット
    state = apply_danger_flag_down(state, events)

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

    # 再発火カウントを更新
    # metricトリガーのみを対象とする
    retrigger_counts = update_retrigger_counts(
        previous_counts=metric_result.new_state.arc_retrigger_counts,
        graph=graph,
        normal_trigger_edges=metric_result.triggered_edges,
        watch_states=metric_result.new_state.arc_watch_states,
        server_time=server_time,
        config=config,
    )

    manual_result = detect_manual_triggers(events=events)
    danger_triggers = tuple(
        FiredTrigger(
            kind=QueuedTriggerKind.DANGER,
            fired_at=server_time,
            origin_edge_id=edge_id,
            snapshot_ref=observations.snapshot_ref,
        )
        for edge_id in manual_result.triggered_edges
    ) + tuple(
        FiredTrigger(
            kind=QueuedTriggerKind.DANGER,
            fired_at=server_time,
            origin_node_id=node_id,
            snapshot_ref=observations.snapshot_ref,
        )
        for node_id in manual_result.triggered_nodes
    )
    danger_evidences: tuple[TriggerEvidence, ...] = tuple(
        DangerEvidence(occurred_at=server_time, edge_id=edge_id)
        for edge_id in manual_result.triggered_edges
    ) + tuple(
        DangerEvidence(occurred_at=server_time, node_id=node_id)
        for node_id in manual_result.triggered_nodes
    )

    decision = evaluate_cooldown(
        previous_state=metric_result.new_state,
        fired_triggers=danger_triggers + metric_result.fired_triggers,
        server_time=server_time,
        config=config,
    )

    new_state = replace(decision.new_state, arc_retrigger_counts=retrigger_counts)
    # 発火時は連続スキップカウントをリセット
    if decision.verdict == VerdictHint.TRIGGERED:
        new_state = replace(new_state, consecutive_skip_count=0)

    # 検出した通常トリガー・危険フラグ・キュー発火条件のEvidenceを統合
    evidences = metric_result.evidences + danger_evidences + decision.evidences

    # 発火を起こすトリガーは常に当該リクエストのもの
    # その時点のスナップショットが「キュー最後の発火時点」に一致
    # 各キューエントリのsnapshot_ref には参照識別子を保持，過去スナップショットの参照に使用する
    return DetectionResult(
        verdict_hint=decision.verdict,
        triggered_edges=decision.triggered_edges,
        triggered_nodes=decision.triggered_nodes,
        effective_snapshot=observations,
        new_state=new_state,
        evidences=evidences,
    )
