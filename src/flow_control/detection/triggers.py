from __future__ import annotations

import statistics
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum

from ..domain import EdgeID, Graph, NodeID
from .config import ResolvedConfig
from .history import ArcHistoryStat, ArcWindowSeries, HistoryDigest
from .observations import ArcScalarFlow, ArcStagnation, Observations
from .state import (
    ArcWatchState,
    DetectionState,
    QueuedTrigger,
    QueuedTriggerKind,
    RetriggerEntry,
    WarmupState,
)

EPSILON_FLOW = 1e-6

_TARGET_PREFIX_EDGE = "edge:"
_TARGET_PREFIX_NODE = "node:"


class EventKind(str, Enum):
    DANGER_FLAG_UP = "DANGER_FLAG_UP"
    DANGER_FLAG_DOWN = "DANGER_FLAG_DOWN"
    DIRECTION_SWITCH = "DIRECTION_SWITCH"
    ADD_EDGE = "ADD_EDGE"
    ADD_NODE = "ADD_NODE"
    DISABLE = "DISABLE"
    ENABLE = "ENABLE"
    SCHEDULED_INFLOW = "SCHEDULED_INFLOW"
    SCHEDULED_ATTR_CHANGE = "SCHEDULED_ATTR_CHANGE"


@dataclass(frozen=True)
class Event:
    """
    ``"edge:<edge_id>"``: アーク対象
    ``"node:<node_id>"``: ノード対象
    """

    kind: EventKind
    target_id: str
    occurred_at: datetime


@dataclass(frozen=True)
class MetricTriggerDetectionResult:
    triggered_edges: tuple[EdgeID, ...]
    fired_triggers: tuple[FiredTrigger, ...]
    new_state: DetectionState


def detect_metric_triggers(
    graph: Graph,
    observations: Observations,
    history_digest: HistoryDigest,
    previous_state: DetectionState,
    server_time: datetime,
    config: ResolvedConfig,
) -> MetricTriggerDetectionResult:
    triggered_edges: list[EdgeID] = []
    fired_triggers: list[FiredTrigger] = []
    new_watch_states: list[ArcWatchState] = []

    for edge in graph.enabled_edges():
        # ウォームアップ中の対象はトリガー判定を停止
        if previous_state.is_in_warmup(_edge_target_key(edge.edge_id), server_time):
            continue

        surge_fired = _evaluate_surge_trigger(
            edge.time_resolution_s,
            observations.observed_at,
            observations.scalar_flow_of(edge.edge_id),
            history_digest.window_series_of(edge.edge_id),
            config.surge_rate_threshold_percent_per_min,
            config.surge_evaluate_window_minute,
            server_time,
        )

        stagnation_fired, next_watch = _evaluate_high_stagnation_trigger(
            edge.edge_id,
            observations.stagnation_of(edge.edge_id),
            history_digest.stat_of(edge.edge_id),
            previous_state.watch_state_of(edge.edge_id),
            config.high_stagnation_duration_min,
            config.beta,
            server_time,
        )

        if surge_fired:
            fired_triggers.append(
                FiredTrigger(
                    kind=QueuedTriggerKind.SURGE,
                    fired_at=server_time,
                    origin_edge_id=edge.edge_id,
                )
            )
        if stagnation_fired:
            fired_triggers.append(
                FiredTrigger(
                    kind=QueuedTriggerKind.HIGH_STAGNATION,
                    fired_at=server_time,
                    origin_edge_id=edge.edge_id,
                )
            )
        if surge_fired or stagnation_fired:
            triggered_edges.append(edge.edge_id)
        if next_watch is not None:
            new_watch_states.append(next_watch)

    new_state = replace(previous_state, arc_watch_states=tuple(new_watch_states))

    return MetricTriggerDetectionResult(
        triggered_edges=tuple(triggered_edges),
        fired_triggers=tuple(fired_triggers),
        new_state=new_state,
    )


def _evaluate_surge_trigger(
    edge_resolution_s: float,
    observed_at: datetime,
    observed_scaler_flow: ArcScalarFlow | None,
    history_series: ArcWindowSeries | None,
    threshold_per_min: float,
    evaluate_window_minute: float,
    server_time: datetime,
) -> bool:
    window_minute = evaluate_window_minute + edge_resolution_s / 60.0
    window_start_time = server_time - timedelta(minutes=window_minute)

    if history_series is None:
        return False

    series = [(t, v) for (t, v) in history_series.samples if t >= window_start_time]

    if observed_scaler_flow is not None and observed_at >= window_start_time:
        series.append((observed_at, observed_scaler_flow.observed_count))

    if len(series) < 2:
        return False

    (first_time, _) = series[0]
    xs = [(t - first_time).total_seconds() / 60.0 for (t, _) in series]
    ys = [v for (_, v) in series]
    x_mean = statistics.mean(xs)
    y_mean = statistics.mean(ys)

    num = sum((x - x_mean) * (y - y_mean) for (x, y) in zip(xs, ys))
    den = sum((x - x_mean) ** 2 for x in xs)

    if den < EPSILON_FLOW:
        return False
    slope = num / den

    if y_mean < EPSILON_FLOW:
        return False
    rate_per_min = (slope / y_mean) * 100.0

    if rate_per_min > threshold_per_min:
        return True

    return False


def _evaluate_high_stagnation_trigger(
    edge_id: EdgeID,
    observed_stagnation: ArcStagnation | None,
    history_stat: ArcHistoryStat | None,
    previous_watch: ArcWatchState | None,
    high_stagnation_duration_min: float,
    beta: float,
    server_time: datetime,
) -> tuple[bool, ArcWatchState | None]:
    if observed_stagnation is None or history_stat is None:
        return False, previous_watch

    stagnation = observed_stagnation.stagnation
    p90 = history_stat.p90_stagnation
    baseline = history_stat.baseline_stagnation

    percentile_breached = p90 is not None and stagnation >= p90
    delta_breached = baseline is not None and (stagnation - baseline) >= beta

    if not percentile_breached and not delta_breached:
        return False, None

    if percentile_breached and delta_breached:
        prev_both_breached = (
            previous_watch is not None
            and previous_watch.percentile_breached
            and previous_watch.delta_breached
            and previous_watch.started_at is not None
        )
        if prev_both_breached:
            assert previous_watch is not None and previous_watch.started_at is not None
            elapsed_minutes = (
                server_time - previous_watch.started_at
            ).total_seconds() / 60.0
            if elapsed_minutes >= high_stagnation_duration_min:
                return True, None
            return False, ArcWatchState(
                edge_id=edge_id,
                percentile_breached=True,
                delta_breached=True,
                started_at=previous_watch.started_at,
            )
        return False, ArcWatchState(
            edge_id=edge_id,
            percentile_breached=True,
            delta_breached=True,
            started_at=server_time,
        )

    same_partial_configuration = (
        previous_watch is not None
        and previous_watch.percentile_breached == percentile_breached
        and previous_watch.delta_breached == delta_breached
        and previous_watch.started_at is not None
    )
    if same_partial_configuration:
        assert previous_watch is not None
        return False, ArcWatchState(
            edge_id=edge_id,
            percentile_breached=percentile_breached,
            delta_breached=delta_breached,
            started_at=previous_watch.started_at,
        )
    return False, ArcWatchState(
        edge_id=edge_id,
        percentile_breached=percentile_breached,
        delta_breached=delta_breached,
        started_at=server_time,
    )


@dataclass(frozen=True)
class ManualTriggerDetectionResult:
    triggered_edges: tuple[EdgeID, ...]
    triggered_nodes: tuple[NodeID, ...]


def detect_manual_triggers(
    events: tuple[Event, ...],
) -> ManualTriggerDetectionResult:
    triggered_edges: list[EdgeID] = []
    triggered_nodes: list[NodeID] = []
    seen_edges: set[EdgeID] = set()
    seen_nodes: set[NodeID] = set()

    for event in events:
        if event.kind != EventKind.DANGER_FLAG_UP:
            continue
        if event.target_id.startswith(_TARGET_PREFIX_EDGE):
            edge_id = EdgeID(event.target_id[len(_TARGET_PREFIX_EDGE) :])
            if edge_id not in seen_edges:
                seen_edges.add(edge_id)
                triggered_edges.append(edge_id)
        elif event.target_id.startswith(_TARGET_PREFIX_NODE):
            node_id = NodeID(event.target_id[len(_TARGET_PREFIX_NODE) :])
            if node_id not in seen_nodes:
                seen_nodes.add(node_id)
                triggered_nodes.append(node_id)

    return ManualTriggerDetectionResult(
        triggered_edges=tuple(triggered_edges),
        triggered_nodes=tuple(triggered_nodes),
    )


class VerdictHint(str, Enum):
    TRIGGERED = "TRIGGERED"
    QUEUED = "QUEUED"
    SKIPPED_COOLDOWN = "SKIPPED_COOLDOWN"
    SKIPPED_WARMUP = "SKIPPED_WARMUP"
    NO_TRIGGER = "NO_TRIGGER"


@dataclass(frozen=True)
class FiredTrigger:
    kind: QueuedTriggerKind
    fired_at: datetime
    origin_edge_id: EdgeID | None = None
    origin_node_id: NodeID | None = None
    score: float = 1.0


@dataclass(frozen=True)
class CooldownDecision:
    verdict: VerdictHint
    triggered_edges: tuple[EdgeID, ...]
    triggered_nodes: tuple[NodeID, ...]
    new_state: DetectionState


def evaluate_cooldown(
    previous_state: DetectionState,
    fired_triggers: tuple[FiredTrigger, ...],
    server_time: datetime,
    config: ResolvedConfig,
) -> CooldownDecision:
    danger_triggers = tuple(
        t for t in fired_triggers if t.kind == QueuedTriggerKind.DANGER
    )
    normal_triggers = tuple(
        t for t in fired_triggers if t.kind != QueuedTriggerKind.DANGER
    )

    if previous_state.is_in_cooldown(server_time):
        if danger_triggers:
            # 危険フラグはクールタイム中でも即時発火
            return _fire(
                previous_state,
                server_time,
                config,
                previous_state.trigger_queue,
                fired_triggers,
            )
        if normal_triggers:
            merged_queue = _merge_into_queue(
                previous_state.trigger_queue, normal_triggers
            )
            if _queue_exceeds_score(merged_queue, config) or _queue_is_diverse(
                merged_queue, config
            ):
                # スコア超過 or 多様性超過
                return _fire(previous_state, server_time, config, merged_queue)
            queued_state = replace(previous_state, trigger_queue=merged_queue)
            return CooldownDecision(VerdictHint.QUEUED, (), (), queued_state)
        # クールタイム中，トリガーなし
        return CooldownDecision(VerdictHint.SKIPPED_COOLDOWN, (), (), previous_state)

    # クールタイム外，トリガーがあれば発火，なければ未検出
    if fired_triggers:
        return _fire(
            previous_state,
            server_time,
            config,
            previous_state.trigger_queue,
            fired_triggers,
        )
    return CooldownDecision(VerdictHint.NO_TRIGGER, (), (), previous_state)


def _fire(
    previous_state: DetectionState,
    server_time: datetime,
    config: ResolvedConfig,
    *origin_sources: tuple[object, ...],
) -> CooldownDecision:
    triggered_edges = _distinct_origin_edges(origin_sources)
    triggered_nodes = _distinct_origin_nodes(origin_sources)
    cooldown_until = server_time + timedelta(minutes=config.cooldown_duration_min)
    new_state = replace(previous_state, cooldown_until=cooldown_until, trigger_queue=())
    return CooldownDecision(
        VerdictHint.TRIGGERED, triggered_edges, triggered_nodes, new_state
    )


def _merge_into_queue(
    queue: tuple[QueuedTrigger, ...],
    normal_triggers: tuple[FiredTrigger, ...],
) -> tuple[QueuedTrigger, ...]:
    merged: list[QueuedTrigger] = list(queue)
    for trigger in normal_triggers:
        index = _find_same_route(merged, trigger)
        if index is None:
            merged.append(
                QueuedTrigger(
                    kind=trigger.kind,
                    first_fired_at=trigger.fired_at,
                    last_fired_at=trigger.fired_at,
                    accumulated_score=trigger.score,
                    origin_edge_id=trigger.origin_edge_id,
                    origin_node_id=trigger.origin_node_id,
                )
            )
        else:
            existing = merged[index]
            merged[index] = QueuedTrigger(
                kind=existing.kind,
                first_fired_at=existing.first_fired_at,
                last_fired_at=trigger.fired_at,
                accumulated_score=existing.accumulated_score + trigger.score,
                origin_edge_id=existing.origin_edge_id,
                origin_node_id=existing.origin_node_id,
            )
    return tuple(merged)


def _find_same_route(queue: list[QueuedTrigger], trigger: FiredTrigger) -> int | None:
    for index, entry in enumerate(queue):
        if (
            entry.origin_edge_id == trigger.origin_edge_id
            and entry.origin_node_id == trigger.origin_node_id
        ):
            return index
    return None


def _queue_exceeds_score(
    queue: tuple[QueuedTrigger, ...], config: ResolvedConfig
) -> bool:
    total = sum(entry.accumulated_score for entry in queue)
    return total > config.queue_score_threshold


def _queue_is_diverse(queue: tuple[QueuedTrigger, ...], config: ResolvedConfig) -> bool:
    distinct_edges = {
        entry.origin_edge_id for entry in queue if entry.origin_edge_id is not None
    }
    return len(distinct_edges) > config.queue_diversity_threshold


def _distinct_origin_edges(
    origin_sources: tuple[tuple[object, ...], ...],
) -> tuple[EdgeID, ...]:
    seen: set[EdgeID] = set()
    ordered: list[EdgeID] = []
    for source in origin_sources:
        for item in source:
            edge_id = getattr(item, "origin_edge_id", None)
            if edge_id is not None and edge_id not in seen:
                seen.add(edge_id)
                ordered.append(edge_id)
    return tuple(ordered)


def _distinct_origin_nodes(
    origin_sources: tuple[tuple[object, ...], ...],
) -> tuple[NodeID, ...]:
    seen: set[NodeID] = set()
    ordered: list[NodeID] = []
    for source in origin_sources:
        for item in source:
            node_id = getattr(item, "origin_node_id", None)
            if node_id is not None and node_id not in seen:
                seen.add(node_id)
                ordered.append(node_id)
    return tuple(ordered)


def _edge_target_key(edge_id: EdgeID) -> str:
    return f"{_TARGET_PREFIX_EDGE}{edge_id.value}"


def _node_target_key(node_id: NodeID) -> str:
    return f"{_TARGET_PREFIX_NODE}{node_id.value}"


# 新規登場／有効化でウォームアップを開始するイベント種別
_WARMUP_EVENT_KINDS = (
    EventKind.ENABLE,
    EventKind.ADD_EDGE,
    EventKind.ADD_NODE,
)


def apply_warmup_events(
    previous_state: DetectionState,
    events: tuple[Event, ...],
    server_time: datetime,
    config: ResolvedConfig,
) -> DetectionState:
    # ENABLE/ADD_* を受けた対象に server_time + warmup_duration を設定
    warmup_until = server_time + timedelta(minutes=config.warmup_duration_min)
    warmup_map = {w.target_key: w.until for w in previous_state.warmup_states}
    for event in events:
        if event.kind in _WARMUP_EVENT_KINDS:
            warmup_map[event.target_id] = warmup_until

    if warmup_map == {w.target_key: w.until for w in previous_state.warmup_states}:
        return previous_state

    warmup_states = tuple(
        WarmupState(target_key=key, until=until) for key, until in warmup_map.items()
    )
    return replace(previous_state, warmup_states=warmup_states)


# 状態変化としてクールタイムをリセットするスケジュールイベント種別
_SCHEDULED_EVENT_KINDS = (
    EventKind.SCHEDULED_INFLOW,
    EventKind.SCHEDULED_ATTR_CHANGE,
)


def apply_scheduled_events(
    previous_state: DetectionState,
    events: tuple[Event, ...],
) -> DetectionState:
    # スケジュールイベントはクールタイムをリセットする，キューは保持
    has_scheduled = any(event.kind in _SCHEDULED_EVENT_KINDS for event in events)
    if not has_scheduled or previous_state.cooldown_until is None:
        return previous_state
    return replace(previous_state, cooldown_until=None)


def all_targets_in_warmup(
    state: DetectionState,
    graph: Graph,
    server_time: datetime,
) -> bool:
    # 有効なアーク・ノード全対象がウォームアップ中か
    # 対象ゼロは False
    target_keys = [_edge_target_key(e.edge_id) for e in graph.enabled_edges()]
    target_keys += [_node_target_key(n.node_id) for n in graph.enabled_nodes()]
    if not target_keys:
        return False
    return all(state.is_in_warmup(key, server_time) for key in target_keys)


def has_danger_event(events: tuple[Event, ...]) -> bool:
    return any(event.kind == EventKind.DANGER_FLAG_UP for event in events)


def update_retrigger_counts(
    previous_counts: tuple[RetriggerEntry, ...],
    graph: Graph,
    normal_trigger_edges: tuple[EdgeID, ...],
    watch_states: tuple[ArcWatchState, ...],
    server_time: datetime,
    config: ResolvedConfig,
) -> tuple[RetriggerEntry, ...]:
    # 再発火カウントのリセット
    # 手動トリガーはカウント対象外
    fired_edges = list(dict.fromkeys(normal_trigger_edges))  # 出現順・重複排除
    fired_set = set(fired_edges)
    watched = {
        watch.edge_id
        for watch in watch_states
        if watch.percentile_breached or watch.delta_breached
    }
    enabled_edges = {edge.edge_id for edge in graph.enabled_edges()}

    entries: dict[EdgeID, RetriggerEntry] = {}
    for entry in previous_counts:
        edge_id = entry.edge_id
        if edge_id not in enabled_edges:
            # グラフ削除／無効化 → エントリ削除
            continue

        fired_this_cycle = edge_id in fired_set
        different_origin = bool(fired_set - {edge_id})

        if different_origin and not fired_this_cycle:
            # 別アーク起点発火 → 当該アークのカウントをリセット
            entries[edge_id] = RetriggerEntry(
                edge_id=edge_id, last_fired_at=entry.last_fired_at
            )
        elif not fired_this_cycle and edge_id not in watched:
            quiet_cycles = entry.quiet_cycles + 1
            if quiet_cycles >= config.retrigger_reset_quiet_cycles:
                # 連続沈静化 → リセット
                entries[edge_id] = RetriggerEntry(
                    edge_id=edge_id, last_fired_at=entry.last_fired_at
                )
            else:
                entries[edge_id] = RetriggerEntry(
                    edge_id=edge_id,
                    count=entry.count,
                    quiet_cycles=quiet_cycles,
                    last_fired_at=entry.last_fired_at,
                )
        elif fired_this_cycle:
            entries[edge_id] = RetriggerEntry(
                edge_id=edge_id,
                count=entry.count + 1,
                quiet_cycles=0,
                last_fired_at=server_time,
            )
        else:
            # 発火せず警戒中かつ別起点発火なし → カウント維持
            entries[edge_id] = entry

    # 初回発火のアーク（既存エントリなし）は count=1 で登録
    for edge_id in fired_edges:
        if edge_id in entries or edge_id not in enabled_edges:
            continue
        entries[edge_id] = RetriggerEntry(
            edge_id=edge_id, count=1, quiet_cycles=0, last_fired_at=server_time
        )

    return tuple(entries.values())


def apply_danger_flag_down(
    previous_state: DetectionState,
    events: tuple[Event, ...],
) -> DetectionState:
    # DANGER_FLAG_DOWN を受けたアークの既存の再発火カウントリセット
    # 立ち下げ自体は発火扱いとしない
    # クールタイムリセットも行わない
    cleared_edges = {
        EdgeID(event.target_id[len(_TARGET_PREFIX_EDGE) :])
        for event in events
        if event.kind == EventKind.DANGER_FLAG_DOWN
        and event.target_id.startswith(_TARGET_PREFIX_EDGE)
    }
    if not cleared_edges:
        return previous_state

    changed = False
    updated: list[RetriggerEntry] = []
    for entry in previous_state.arc_retrigger_counts:
        if entry.edge_id in cleared_edges and (entry.count or entry.quiet_cycles):
            updated.append(
                RetriggerEntry(edge_id=entry.edge_id, last_fired_at=entry.last_fired_at)
            )
            changed = True
        else:
            updated.append(entry)

    if not changed:
        return previous_state
    return replace(previous_state, arc_retrigger_counts=tuple(updated))
