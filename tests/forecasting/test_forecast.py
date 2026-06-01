"""``forecast`` の Open モード統合テスト（観測 → 粗流出入 → 重力配分）"""

from datetime import datetime, timezone

import pytest

from flow_control.domain import (
    ArcFlow,
    CurrentDirection,
    DirectionConstraint,
    Edge,
    EdgeID,
    FlowDirection,
    Graph,
    HistoryDigest,
    Node,
    NodeID,
    NodeKind,
    Observations,
    ObservationType,
    Reference,
)
from flow_control.forecasting import forecast
from flow_control.forecasting.config import ResolvedConfig


def _vector_edge(edge_id: str, a: str, b: str) -> Edge:
    return Edge(
        edge_id=EdgeID(edge_id),
        endpoint_a=NodeID(a),
        endpoint_b=NodeID(b),
        direction_constraint=DirectionConstraint.BIDIRECTIONAL_PRIOR,
        current_direction=CurrentDirection.BIDIRECTIONAL,
        enabled=True,
        observation_type=ObservationType.VECTOR,
    )


def test_forecast_open_mode_builds_od_matrix() -> None:
    """境界 entrance(+10) → 内部 hall(-6) に重力配分される
    境界 exit は除外

    entrance->hall=10, hall->exit=4 →
      entrance: b=+10（Source/境界）, hall: b=-6（Sink/内部）, exit: b=-4（Sink/境界）
    Source entrance は境界のため境界 Sink(exit) を除外し，hall に全量 10 を配分
    """
    graph = Graph(
        nodes=(
            Node(
                node_id=NodeID("entrance"),
                kind=NodeKind.GOAL,
                is_boundary=True,
                enabled=True,
            ),
            Node(
                node_id=NodeID("hall"),
                kind=NodeKind.GOAL,
                is_boundary=False,
                enabled=True,
            ),
            Node(
                node_id=NodeID("exit"),
                kind=NodeKind.GOAL,
                is_boundary=True,
                enabled=True,
            ),
        ),
        edges=(
            _vector_edge("e1", "entrance", "hall"),
            _vector_edge("e2", "hall", "exit"),
        ),
    )
    observations = Observations(
        observed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        arc_flows=(
            ArcFlow(
                edge_id=EdgeID("e1"), direction=FlowDirection.A_TO_B, flow_rate=10.0
            ),
            ArcFlow(
                edge_id=EdgeID("e2"), direction=FlowDirection.A_TO_B, flow_rate=4.0
            ),
        ),
    )
    config = ResolvedConfig(min_reference_sample_count=5, fallback_eta=1.0)

    result = forecast(
        graph=graph,
        observations=observations,
        history_digest=HistoryDigest(),
        references=Reference(),
        triggered_edges=(),
        config=config,
    )

    assert len(result.od_matrix) == 1
    od = result.od_matrix[0]
    assert od.origin == NodeID("entrance")
    assert od.destination == NodeID("hall")
    assert od.demand == pytest.approx(10.0)


def test_forecast_closed_mode_od_matrix_empty_for_now() -> None:
    """境界ノードが無い Closed モードは現状 OD 空（IPF 未実装）"""
    graph = Graph(
        nodes=(
            Node(
                node_id=NodeID("a"), kind=NodeKind.GOAL, is_boundary=False, enabled=True
            ),
            Node(
                node_id=NodeID("b"), kind=NodeKind.GOAL, is_boundary=False, enabled=True
            ),
        ),
        edges=(_vector_edge("e1", "a", "b"),),
    )
    observations = Observations(
        observed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        arc_flows=(
            ArcFlow(
                edge_id=EdgeID("e1"), direction=FlowDirection.A_TO_B, flow_rate=5.0
            ),
        ),
    )
    config = ResolvedConfig(min_reference_sample_count=5, fallback_eta=1.0)

    result = forecast(
        graph=graph,
        observations=observations,
        history_digest=HistoryDigest(),
        references=Reference(),
        triggered_edges=(),
        config=config,
    )

    assert result.od_matrix == ()
