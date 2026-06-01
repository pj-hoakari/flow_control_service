"""``compute_node_flow_balances`` のテスト"""

from datetime import datetime, timezone

import pytest

from flow_control.domain import (
    ArcFlow,
    ConfidenceFlag,
    CurrentDirection,
    DirectionConstraint,
    Edge,
    EdgeID,
    FlowDirection,
    Graph,
    Node,
    NodeID,
    NodeKind,
    Observations,
    ObservationType,
)
from flow_control.forecasting.demand import (
    NodeFlowBalance,
    compute_node_flow_balances,
)


@pytest.fixture
def observed_at() -> datetime:
    return datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)


def _node(node_id: str, *, enabled: bool = True) -> Node:
    return Node(
        node_id=NodeID(node_id),
        kind=NodeKind.GOAL,
        is_boundary=False,
        enabled=enabled,
    )


def _edge(
    edge_id: str,
    a: str,
    b: str,
    *,
    enabled: bool = True,
    observation_type: ObservationType = ObservationType.VECTOR,
) -> Edge:
    return Edge(
        edge_id=EdgeID(edge_id),
        endpoint_a=NodeID(a),
        endpoint_b=NodeID(b),
        direction_constraint=DirectionConstraint.BIDIRECTIONAL_PRIOR,
        current_direction=CurrentDirection.BIDIRECTIONAL,
        enabled=enabled,
        observation_type=observation_type,
    )


def _balance_of(balances: tuple[NodeFlowBalance, ...], node_id: str) -> NodeFlowBalance:
    for balance in balances:
        if balance.node_id == NodeID(node_id):
            return balance
    raise AssertionError(f"node {node_id} not found in balances")


def test_single_edge_a_to_b(observed_at: datetime) -> None:
    """A_TO_B: endpoint_a が粗流出，endpoint_b が粗流入"""
    graph = Graph(nodes=(_node("n1"), _node("n2")), edges=(_edge("e1", "n1", "n2"),))
    observations = Observations(
        observed_at=observed_at,
        arc_flows=(
            ArcFlow(
                edge_id=EdgeID("e1"), direction=FlowDirection.A_TO_B, flow_rate=4.0
            ),
        ),
    )

    balances = compute_node_flow_balances(graph, observations)

    n1 = _balance_of(balances, "n1")
    n2 = _balance_of(balances, "n2")
    assert (n1.gross_outflow, n1.gross_inflow) == (4.0, 0.0)
    assert (n2.gross_outflow, n2.gross_inflow) == (0.0, 4.0)
    assert n1.net_demand == 4.0  # Source
    assert n2.net_demand == -4.0  # Sink


def test_single_edge_b_to_a(observed_at: datetime) -> None:
    """B_TO_A: 流出元・流入先が反転する"""
    graph = Graph(nodes=(_node("n1"), _node("n2")), edges=(_edge("e1", "n1", "n2"),))
    observations = Observations(
        observed_at=observed_at,
        arc_flows=(
            ArcFlow(
                edge_id=EdgeID("e1"), direction=FlowDirection.B_TO_A, flow_rate=3.0
            ),
        ),
    )

    balances = compute_node_flow_balances(graph, observations)

    assert _balance_of(balances, "n2").gross_outflow == 3.0
    assert _balance_of(balances, "n1").gross_inflow == 3.0


def test_scalar_edge_excluded(observed_at: datetime) -> None:
    """スカラー型アークは集計対象外"""
    graph = Graph(
        nodes=(_node("n1"), _node("n2")),
        edges=(_edge("e1", "n1", "n2", observation_type=ObservationType.SCALAR),),
    )
    observations = Observations(
        observed_at=observed_at,
        arc_flows=(
            ArcFlow(
                edge_id=EdgeID("e1"), direction=FlowDirection.A_TO_B, flow_rate=9.0
            ),
        ),
    )

    balances = compute_node_flow_balances(graph, observations)

    assert all(b.gross_outflow == 0.0 and b.gross_inflow == 0.0 for b in balances)


def test_invalid_confidence_excluded_hold_included(observed_at: datetime) -> None:
    """INVALID は需要寄与なし，HOLD は全量寄与"""
    graph = Graph(
        nodes=(_node("n1"), _node("n2"), _node("n3")),
        edges=(_edge("e1", "n1", "n2"), _edge("e2", "n2", "n3")),
    )
    observations = Observations(
        observed_at=observed_at,
        arc_flows=(
            ArcFlow(
                edge_id=EdgeID("e1"),
                direction=FlowDirection.A_TO_B,
                flow_rate=5.0,
                confidence_flag=ConfidenceFlag.INVALID,
            ),
            ArcFlow(
                edge_id=EdgeID("e2"),
                direction=FlowDirection.A_TO_B,
                flow_rate=7.0,
                confidence_flag=ConfidenceFlag.HOLD,
            ),
        ),
    )

    balances = compute_node_flow_balances(graph, observations)

    # INVALID の e1 は寄与なし → n1 は全てゼロ
    n1 = _balance_of(balances, "n1")
    assert (n1.gross_outflow, n1.gross_inflow) == (0.0, 0.0)
    # HOLD の e2 は全量寄与
    assert _balance_of(balances, "n2").gross_outflow == 7.0
    assert _balance_of(balances, "n3").gross_inflow == 7.0


def test_disabled_edge_excluded(observed_at: datetime) -> None:
    """無効エッジの観測は無視"""
    graph = Graph(
        nodes=(_node("n1"), _node("n2")),
        edges=(_edge("e1", "n1", "n2", enabled=False),),
    )
    observations = Observations(
        observed_at=observed_at,
        arc_flows=(
            ArcFlow(
                edge_id=EdgeID("e1"), direction=FlowDirection.A_TO_B, flow_rate=5.0
            ),
        ),
    )

    balances = compute_node_flow_balances(graph, observations)

    assert all(b.gross_outflow == 0.0 and b.gross_inflow == 0.0 for b in balances)


def test_unknown_edge_ignored(observed_at: datetime) -> None:
    """グラフに存在しないエッジを指す観測は無視"""
    graph = Graph(nodes=(_node("n1"), _node("n2")), edges=(_edge("e1", "n1", "n2"),))
    observations = Observations(
        observed_at=observed_at,
        arc_flows=(
            ArcFlow(
                edge_id=EdgeID("e_unknown"),
                direction=FlowDirection.A_TO_B,
                flow_rate=5.0,
            ),
        ),
    )

    balances = compute_node_flow_balances(graph, observations)

    assert all(b.gross_outflow == 0.0 and b.gross_inflow == 0.0 for b in balances)


def test_aggregation_at_shared_node(observed_at: datetime) -> None:
    """中心ノードで複数アークの流入・流出が合算される（Y 型）

    e1: nc->n1 (A_TO_B, 2.0), e2: nc->n2 (A_TO_B, 3.0) → nc は粗流出 5.0
    e3: n3->nc は B_TO_A 4.0 で nc へ流入 → nc は粗流入 4.0
    """
    graph = Graph(
        nodes=(_node("nc"), _node("n1"), _node("n2"), _node("n3")),
        edges=(
            _edge("e1", "nc", "n1"),
            _edge("e2", "nc", "n2"),
            _edge("e3", "nc", "n3"),
        ),
    )
    observations = Observations(
        observed_at=observed_at,
        arc_flows=(
            ArcFlow(
                edge_id=EdgeID("e1"), direction=FlowDirection.A_TO_B, flow_rate=2.0
            ),
            ArcFlow(
                edge_id=EdgeID("e2"), direction=FlowDirection.A_TO_B, flow_rate=3.0
            ),
            ArcFlow(
                edge_id=EdgeID("e3"), direction=FlowDirection.B_TO_A, flow_rate=4.0
            ),
        ),
    )

    balances = compute_node_flow_balances(graph, observations)

    nc = _balance_of(balances, "nc")
    assert nc.gross_outflow == 5.0
    assert nc.gross_inflow == 4.0
    assert nc.net_demand == 1.0


def test_disabled_node_excluded_and_ordering(observed_at: datetime) -> None:
    """無効ノードは結果に含まれず，順序は enabled_nodes() の順に従う"""
    graph = Graph(
        nodes=(_node("n1"), _node("n2", enabled=False), _node("n3")),
        edges=(_edge("e1", "n1", "n3"),),
    )
    observations = Observations(observed_at=observed_at)

    balances = compute_node_flow_balances(graph, observations)

    assert tuple(b.node_id for b in balances) == (NodeID("n1"), NodeID("n3"))
