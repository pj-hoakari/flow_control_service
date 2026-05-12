"""Common factories for Detection tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from flow_control.models import (
    ArcFlow,
    ArcHistoryStat,
    ArcStagnation,
    ArcWindowSeries,
    ConfidenceFlag,
    CurrentDirection,
    DetectionState,
    DirectionConstraint,
    Edge,
    FlowDirection,
    Graph,
    HistoryDigest,
    Node,
    NodeKind,
    Observations,
    ObservationType,
    Reference,
    ResolvedConfig,
    TenantCategory,
    TenantContext,
)


def make_node(node_id: str, *, is_boundary: bool = False, enabled: bool = True) -> Node:
    return Node(
        node_id=node_id,
        kind=NodeKind.GOAL,
        is_boundary=is_boundary,
        enabled=enabled,
    )


def make_edge(
    edge_id: str,
    endpoint_a: str,
    endpoint_b: str,
    *,
    enabled: bool = True,
    observation_type: ObservationType = ObservationType.VECTOR,
    direction_constraint: DirectionConstraint = DirectionConstraint.BIDIRECTIONAL_PRIOR,
    current_direction: CurrentDirection = CurrentDirection.BIDIRECTIONAL,
) -> Edge:
    return Edge(
        edge_id=edge_id,
        endpoint_a=endpoint_a,
        endpoint_b=endpoint_b,
        direction_constraint=direction_constraint,
        current_direction=current_direction,
        enabled=enabled,
        observation_type=observation_type,
    )


@pytest.fixture
def base_time() -> datetime:
    return datetime(2026, 5, 12, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def basic_graph() -> Graph:
    nodes = (
        make_node("n1", is_boundary=True),
        make_node("n2"),
        make_node("n3"),
    )
    edges = (
        make_edge("e1", "n1", "n2"),
        make_edge("e2", "n2", "n3"),
    )
    return Graph(nodes=nodes, edges=edges)


@pytest.fixture
def long_term_tenant() -> TenantContext:
    return TenantContext(
        tenant_id="t-long",
        tenant_category=TenantCategory.LONG_TERM,
        available_history_hours=240.0,
    )


@pytest.fixture
def short_term_tenant() -> TenantContext:
    return TenantContext(
        tenant_id="t-short",
        tenant_category=TenantCategory.SHORT_TERM,
        available_history_hours=2.0,
    )


@pytest.fixture
def empty_reference() -> Reference:
    return Reference()


@pytest.fixture
def baseline_config() -> ResolvedConfig:
    return ResolvedConfig(
        surge_rate_threshold_percent_per_min=10.0,
        high_stagnation_duration_min=5.0,
        beta=5.0,
        cooldown_duration_min=60.0,
        warmup_duration_min=60.0,
        retrigger_warning_threshold=3,
        retrigger_reset_quiet_cycles=3,
        queue_score_threshold=10.0,
        queue_diversity_threshold=2,
    )


@pytest.fixture
def empty_state() -> DetectionState:
    return DetectionState()


def make_observations(
    *,
    observed_at: datetime,
    arc_stagnations: tuple[ArcStagnation, ...] = (),
    arc_flows: tuple[ArcFlow, ...] = (),
) -> Observations:
    return Observations(
        observed_at=observed_at,
        arc_stagnations=arc_stagnations,
        arc_flows=arc_flows,
    )


def make_history(
    *,
    stats: tuple[ArcHistoryStat, ...] = (),
    window_series: tuple[ArcWindowSeries, ...] = (),
) -> HistoryDigest:
    return HistoryDigest(arc_stats=stats, window_series=window_series, completeness=1.0)


def linear_window(
    edge_id: str,
    *,
    start: datetime,
    samples: int,
    start_value: float,
    slope_per_min: float,
    step_minutes: float = 1.0,
) -> ArcWindowSeries:
    data: list[tuple[datetime, float]] = []
    for i in range(samples):
        t = start + timedelta(minutes=i * step_minutes)
        data.append((t, start_value + slope_per_min * (i * step_minutes)))
    return ArcWindowSeries(edge_id=edge_id, samples=tuple(data))


__all__ = [
    "make_node",
    "make_edge",
    "make_observations",
    "make_history",
    "linear_window",
    "ConfidenceFlag",
    "FlowDirection",
]
