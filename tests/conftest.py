"""Shared fixtures and factory helpers for detection tests."""

from datetime import datetime, timedelta, timezone

import pytest

from flow_control.detection.config import ResolvedConfig
from flow_control.detection.history import ArcWindowSeries
from flow_control.detection.observations import ArcScalarFlow, Observations
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
def make_linear_series():
    """``ArcWindowSeries`` と ``Observations`` を合わせて 1 本の線形系列となる組を生成する

    ``sample_count`` 件のサンプルを ``end_time`` を最終点として
    ``step_minutes`` 間隔で配置する
    系列の最終 1 件を ``Observations.arc_scalar_flows`` として、
    残り ``sample_count - 1`` 件を ``ArcWindowSeries.samples`` として配置する
    """

    def _make(
        edge_id: EdgeID,
        *,
        end_time: datetime,
        sample_count: int,
        start_value: float,
        slope_per_min: float,
        step_minutes: float = 1.0,
    ) -> tuple[ArcWindowSeries, Observations]:
        span = (sample_count - 1) * step_minutes
        start_time = end_time - timedelta(minutes=span)

        history_samples: list[tuple[datetime, float]] = []
        for i in range(sample_count - 1):
            t = start_time + timedelta(minutes=i * step_minutes)
            v = start_value + slope_per_min * (i * step_minutes)
            history_samples.append((t, v))
        window = ArcWindowSeries(edge_id=edge_id, samples=tuple(history_samples))

        last_value = start_value + slope_per_min * span
        observations = Observations(
            observed_at=end_time,
            arc_scalar_flows=(
                ArcScalarFlow(edge_id=edge_id, observed_count=last_value),
            ),
        )

        return window, observations

    return _make


@pytest.fixture
def make_flat_series(make_linear_series):
    """全サンプル同値で構成される線形系列の組 (``slope=0``) を生成する"""

    def _make(
        edge_id: EdgeID,
        *,
        end_time: datetime,
        sample_count: int,
        value: float,
        step_minutes: float = 1.0,
    ) -> tuple[ArcWindowSeries, Observations]:
        return make_linear_series(
            edge_id,
            end_time=end_time,
            sample_count=sample_count,
            start_value=value,
            slope_per_min=0.0,
            step_minutes=step_minutes,
        )

    return _make


@pytest.fixture
def make_scalar_observation():
    """``observed_at`` 時点の単一 ``ArcScalarFlow`` を持つ ``Observations`` を生成する"""

    def _make(
        edge_id: EdgeID,
        *,
        observed_at: datetime,
        observed_count: float,
    ) -> Observations:
        return Observations(
            observed_at=observed_at,
            arc_scalar_flows=(
                ArcScalarFlow(edge_id=edge_id, observed_count=observed_count),
            ),
        )

    return _make
