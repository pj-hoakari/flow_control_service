import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..domain import EdgeID, Graph
from .config import ResolvedConfig
from .history import ArcWindowSeries, HistoryDigest
from .observations import ArcScalarFlow, Observations
from .state import DetectionState

EPSILON_FLOW = 1e-6


@dataclass(frozen=True)
class NormalTriggerDetectionResult:
    triggered_edges: tuple[EdgeID, ...]
    new_state: DetectionState


def detect_normal_triggers(
    graph: Graph,
    observations: Observations,
    history_digest: HistoryDigest,
    previous_state: DetectionState,
    server_time: datetime,
    config: ResolvedConfig,
) -> NormalTriggerDetectionResult:
    for edge in graph.enabled_edges():
        if _evaluate_surge_trigger(
            edge.time_resolution_s,
            observations.observed_at,
            observations.scalar_flow_of(edge.edge_id),
            history_digest.window_series_of(edge.edge_id),
            config.surge_rate_threshold_percent_per_min,
            config.surge_evaluate_window_minute,
            server_time,
        ):
            return NormalTriggerDetectionResult(
                triggered_edges=(edge.edge_id,), new_state=previous_state
            )

    return NormalTriggerDetectionResult(triggered_edges=(), new_state=previous_state)


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
