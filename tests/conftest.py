"""Shared fixtures and factory helpers for detection tests."""

from datetime import datetime, timedelta, timezone

import pytest

from flow_control.detection.config import ResolvedConfig
from flow_control.detection.history import ArcWindowSeries
from flow_control.domain import (
    CurrentDirection,
    DirectionConstraint,
    Edge,
    EdgeID,
    Graph,
    Node,
    NodeID,
    NodeKind,
    ObservationType,
)


@pytest.fixture
def base_time() -> datetime:
    return datetime(2026, 5, 13, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def edge_id() -> EdgeID:
    return EdgeID("e1")


@pytest.fixture
def basic_graph(edge_id: EdgeID) -> Graph:
    """1 本のベクトル型エッジを持つ最小グラフ

    ``time_resolution_s`` は既定値 60 秒
    急増検出窓は ``30 + 60/60 = 31`` 分。
    """
    n1, n2 = NodeID("n1"), NodeID("n2")
    return Graph(
        nodes=(
            Node(node_id=n1, kind=NodeKind.GOAL, is_boundary=True, enabled=True),
            Node(node_id=n2, kind=NodeKind.GOAL, is_boundary=False, enabled=True),
        ),
        edges=(
            Edge(
                edge_id=edge_id,
                endpoint_a=n1,
                endpoint_b=n2,
                direction_constraint=DirectionConstraint.BIDIRECTIONAL_PRIOR,
                current_direction=CurrentDirection.BIDIRECTIONAL,
                enabled=True,
                observation_type=ObservationType.VECTOR,
            ),
        ),
    )


@pytest.fixture
def surge_config() -> ResolvedConfig:
    """急増判定の閾値: 10 %/分."""
    return ResolvedConfig(surge_rate_threshold_percent_per_min=10.0)


@pytest.fixture
def make_linear_window():
    """``end_time`` 終点で ``step_minutes`` 間隔の線形サンプル列を生成する"""

    def _make(
        edge_id: EdgeID,
        *,
        end_time: datetime,
        sample_count: int,
        start_value: float,
        slope_per_min: float,
        step_minutes: float = 1.0,
    ) -> ArcWindowSeries:
        samples: list[tuple[datetime, float]] = []
        span = (sample_count - 1) * step_minutes
        start_time = end_time - timedelta(minutes=span)
        for i in range(sample_count):
            t = start_time + timedelta(minutes=i * step_minutes)
            v = start_value + slope_per_min * (i * step_minutes)
            samples.append((t, v))
        return ArcWindowSeries(edge_id=edge_id, samples=tuple(samples))

    return _make


@pytest.fixture
def make_flat_window(make_linear_window):
    def _make(
        edge_id: EdgeID,
        *,
        end_time: datetime,
        sample_count: int,
        value: float,
        step_minutes: float = 1.0,
    ) -> ArcWindowSeries:
        return make_linear_window(
            edge_id,
            end_time=end_time,
            sample_count=sample_count,
            start_value=value,
            slope_per_min=0.0,
            step_minutes=step_minutes,
        )

    return _make
