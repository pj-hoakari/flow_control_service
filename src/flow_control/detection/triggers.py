import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from ..domain import EdgeID, Graph, NodeID
from .config import ResolvedConfig
from .history import ArcHistoryStat, ArcWindowSeries, HistoryDigest
from .observations import ArcScalarFlow, ArcStagnation, Observations
from .state import ArcWatchState, DetectionState

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
    new_watch_states: list[ArcWatchState] = []

    for edge in graph.enabled_edges():
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

        if surge_fired or stagnation_fired:
            triggered_edges.append(edge.edge_id)
        if next_watch is not None:
            new_watch_states.append(next_watch)

    new_state = DetectionState(
        trigger_queue=previous_state.trigger_queue,
        arc_watch_states=tuple(new_watch_states),
    )

    return MetricTriggerDetectionResult(
        triggered_edges=tuple(triggered_edges),
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
