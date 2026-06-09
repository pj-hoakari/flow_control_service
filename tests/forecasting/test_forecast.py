"""``forecast`` の統合テスト（観測 → Step A 点需要分解 → Step B OD 推定）"""

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
from flow_control.forecasting.demand import NodeDemand


def _node(node_id: str, kind: NodeKind, *, boundary: bool = False) -> Node:
    return Node(node_id=NodeID(node_id), kind=kind, is_boundary=boundary, enabled=True)


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


def _flow(edge_id: str, rate: float) -> ArcFlow:
    return ArcFlow(
        edge_id=EdgeID(edge_id), direction=FlowDirection.A_TO_B, flow_rate=rate
    )


def _config() -> ResolvedConfig:
    return ResolvedConfig(min_reference_sample_count=5, fallback_eta=1.0)


def _demand_of(demands: tuple[NodeDemand, ...], node_id: str) -> NodeDemand:
    for demand in demands:
        if demand.node_id == NodeID(node_id):
            return demand
    raise AssertionError(f"node {node_id} not found in node_demand")


def test_forecast_open_mode_decomposes_then_builds_od() -> None:
    """境界 entrance(生成) → 通過 mid → ゴール hall(吸収) のパイプライン

    e1: entrance->mid=10, e2: mid->hall=10
    Step A:
      entrance(境界/通過): P=10,A=0  → prod=10, absorb=0
      mid(通過):           P=10,A=10 → trans=10, prod=0, absorb=0
      hall(ゴール):         P=0, A=10 → stay=10, absorb=10, prod=0
    Step B: 生成源 entrance → 吸収 hall に全量 10 を配分（mid は通過のみで OD 非生成）
    """
    graph = Graph(
        nodes=(
            _node("entrance", NodeKind.TRANSIT_ONLY, boundary=True),
            _node("mid", NodeKind.TRANSIT_ONLY),
            _node("hall", NodeKind.GOAL),
        ),
        edges=(
            _vector_edge("e1", "entrance", "mid"),
            _vector_edge("e2", "mid", "hall"),
        ),
    )
    observations = Observations(
        observed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        arc_flows=(_flow("e1", 10.0), _flow("e2", 10.0)),
    )

    result = forecast(
        graph=graph,
        observations=observations,
        history_digest=HistoryDigest(),
        references=Reference(),
        triggered_edges=(),
        config=_config(),
    )

    entrance = _demand_of(result.node_demand, "entrance")
    mid = _demand_of(result.node_demand, "mid")
    hall = _demand_of(result.node_demand, "hall")
    assert (entrance.production, entrance.absorption) == (10.0, 0.0)
    assert (mid.transit, mid.production, mid.absorption) == (10.0, 0.0, 0.0)
    assert (hall.staying, hall.absorption, hall.production) == (10.0, 10.0, 0.0)

    assert len(result.od_matrix) == 1
    od = result.od_matrix[0]
    assert od.origin == NodeID("entrance")
    assert od.destination == NodeID("hall")
    assert od.demand == pytest.approx(10.0)


def test_forecast_closed_mode_decomposes_but_od_empty() -> None:
    """Closed モードでも点需要分解は行われる"""
    graph = Graph(
        nodes=(_node("a", NodeKind.GOAL), _node("b", NodeKind.GOAL)),
        edges=(_vector_edge("e1", "a", "b"),),
    )
    observations = Observations(
        observed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        arc_flows=(_flow("e1", 5.0),),
    )

    result = forecast(
        graph=graph,
        observations=observations,
        history_digest=HistoryDigest(),
        references=Reference(),
        triggered_edges=(),
        config=_config(),
    )

    # Step A はモード非依存で実行される
    assert _demand_of(result.node_demand, "a").production == 5.0
    assert _demand_of(result.node_demand, "b").absorption == 5.0
    # Step B（Closed モード両制約 IPF）は未実装
    assert result.od_matrix == ()
