"""``estimate_od_open`` のテスト"""

import pytest

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
from flow_control.forecasting.config import ResolvedConfig
from flow_control.forecasting.demand import (
    NodeDemand,
    ODDemand,
    estimate_od_open,
)


def _node(node_id: str, *, boundary: bool = False, enabled: bool = True) -> Node:
    return Node(
        node_id=NodeID(node_id),
        kind=NodeKind.GOAL,
        is_boundary=boundary,
        enabled=enabled,
    )


def _edge(edge_id: str, a: str, b: str) -> Edge:
    return Edge(
        edge_id=EdgeID(edge_id),
        endpoint_a=NodeID(a),
        endpoint_b=NodeID(b),
        direction_constraint=DirectionConstraint.BIDIRECTIONAL_PRIOR,
        current_direction=CurrentDirection.BIDIRECTIONAL,
        enabled=True,
        observation_type=ObservationType.VECTOR,
    )


def _bal(node_id: str, net: float) -> NodeDemand:
    """net>0 で生成 prod=net の Source，net<0 で吸収 absorb=|net| の Sink を作る

    estimate_od_open は production / absorption のみ参照するため，他フィールドは整合値で埋める
    """
    return NodeDemand(
        node_id=NodeID(node_id),
        gross_out=net if net > 0 else 0.0,
        gross_in=-net if net < 0 else 0.0,
        production=net if net > 0 else 0.0,
        absorption=-net if net < 0 else 0.0,
        transit=0.0,
        staying=-net if net < 0 else 0.0,
    )


def _config(*, alpha: float = 1.0, delta_min: float = 0.5) -> ResolvedConfig:
    return ResolvedConfig(
        min_reference_sample_count=5,
        fallback_eta=1.0,
        gravity_alpha=alpha,
        delta_min=delta_min,
    )


def _find_od(ods: tuple[ODDemand, ...], origin: str, dest: str) -> ODDemand | None:
    for od in ods:
        if od.origin == NodeID(origin) and od.destination == NodeID(dest):
            return od
    return None


def _require_od(ods: tuple[ODDemand, ...], origin: str, dest: str) -> ODDemand:
    od = _find_od(ods, origin, dest)
    assert od is not None, f"OD ({origin} -> {dest}) not found"
    return od


def test_single_source_single_sink() -> None:
    """1 Source・1 Sink: 全供給量が当該 Sink に配分される"""
    graph = Graph(
        nodes=(_node("s", boundary=True), _node("t")),
        edges=(_edge("e1", "s", "t"),),
    )
    balances = (_bal("s", 10.0), _bal("t", -10.0))

    ods = estimate_od_open(graph, balances, _config())

    assert ods == (ODDemand(origin=NodeID("s"), destination=NodeID("t"), demand=10.0),)


def test_single_constraint_conservation_two_sinks() -> None:
    """単制約: Source の供給量は距離減衰に応じて全 Sink に按分され合計が保存される

    line s - t1 - t2 / α=1 / |b_t1|=|b_t2|=5
    w(s,t1)=1/2=0.5, w(s,t2)=1/3 → δ(s,t1)=6.0, δ(s,t2)=4.0（合計=10）
    """
    graph = Graph(
        nodes=(_node("s", boundary=True), _node("t1"), _node("t2")),
        edges=(_edge("e1", "s", "t1"), _edge("e2", "t1", "t2")),
    )
    balances = (_bal("s", 10.0), _bal("t1", -5.0), _bal("t2", -5.0))

    ods = estimate_od_open(graph, balances, _config())

    assert _require_od(ods, "s", "t1").demand == pytest.approx(6.0)
    assert _require_od(ods, "s", "t2").demand == pytest.approx(4.0)
    assert sum(od.demand for od in ods) == pytest.approx(10.0)


def test_boundary_to_boundary_excluded() -> None:
    """外部→外部（境界 Source→境界 Sink）は OD 対象外，内部 Sink にのみ配分

    line t_bnd - s - t_int / s,t_bnd は境界, t_int は内部
    Source s の供給は t_int にのみ流れ，t_bnd には流れない
    """
    graph = Graph(
        nodes=(
            _node("t_bnd", boundary=True),
            _node("s", boundary=True),
            _node("t_int"),
        ),
        edges=(_edge("e1", "t_bnd", "s"), _edge("e2", "s", "t_int")),
    )
    balances = (_bal("s", 10.0), _bal("t_int", -6.0), _bal("t_bnd", -4.0))

    ods = estimate_od_open(graph, balances, _config())

    assert _find_od(ods, "s", "t_bnd") is None  # 境界→境界は除外
    assert _require_od(ods, "s", "t_int").demand == pytest.approx(10.0)


def test_delta_min_cutoff() -> None:
    """δ_{s,t} <= delta_min の微小 OD はカット

    s=+10, t1=-9.9, t2=-0.1（同距離）→ δ(s,t1)=9.9, δ(s,t2)=0.1
    delta_min=0.5 で t2 は除外
    """
    graph = Graph(
        nodes=(_node("s", boundary=True), _node("t1"), _node("t2")),
        edges=(_edge("e1", "s", "t1"), _edge("e2", "s", "t2")),
    )
    balances = (_bal("s", 10.0), _bal("t1", -9.9), _bal("t2", -0.1))

    ods = estimate_od_open(graph, balances, _config(delta_min=0.5))

    assert _find_od(ods, "s", "t2") is None
    assert _require_od(ods, "s", "t1").demand == pytest.approx(9.9)


def test_unreachable_sink_skipped() -> None:
    """到達不能な Sink には配分しない（到達可能 Sink のみで保存）

    s - t（連結），u は孤立した別成分
    """
    graph = Graph(
        nodes=(_node("s", boundary=True), _node("t"), _node("u")),
        edges=(_edge("e1", "s", "t"),),
    )
    balances = (_bal("s", 10.0), _bal("t", -5.0), _bal("u", -5.0))

    ods = estimate_od_open(graph, balances, _config())

    assert _find_od(ods, "s", "u") is None
    assert _require_od(ods, "s", "t").demand == pytest.approx(10.0)


def test_alpha_distance_decay() -> None:
    """α を大きくすると遠方 Sink への配分が減る

    line s - t1 - t2 / α=2 / |b|=5 ずつ
    w(s,t1)=1/2^2=0.25, w(s,t2)=1/3^2=1/9 → δ(s,t1)≈6.923, δ(s,t2)≈3.077
    """
    graph = Graph(
        nodes=(_node("s", boundary=True), _node("t1"), _node("t2")),
        edges=(_edge("e1", "s", "t1"), _edge("e2", "t1", "t2")),
    )
    balances = (_bal("s", 10.0), _bal("t1", -5.0), _bal("t2", -5.0))

    ods = estimate_od_open(graph, balances, _config(alpha=2.0))

    near = _require_od(ods, "s", "t1").demand
    far = _require_od(ods, "s", "t2").demand
    assert near == pytest.approx(10.0 * 0.25 / (0.25 + 1.0 / 9.0))
    assert far == pytest.approx(10.0 * (1.0 / 9.0) / (0.25 + 1.0 / 9.0))
    assert near > far


def test_no_source_returns_empty() -> None:
    """Source（b_v>0）が無ければ空"""
    graph = Graph(
        nodes=(_node("s", boundary=True), _node("t")),
        edges=(_edge("e1", "s", "t"),),
    )
    balances = (_bal("s", 0.0), _bal("t", -10.0))

    assert estimate_od_open(graph, balances, _config()) == ()


def test_no_sink_returns_empty() -> None:
    """Sink（b_v<0）が無ければ空"""
    graph = Graph(
        nodes=(_node("s", boundary=True), _node("t")),
        edges=(_edge("e1", "s", "t"),),
    )
    balances = (_bal("s", 10.0), _bal("t", 0.0))

    assert estimate_od_open(graph, balances, _config()) == ()


def test_internal_source_routes_to_boundary_sink() -> None:
    """内部 Source→境界 Sink（内部→外部）は対象となる"""
    graph = Graph(
        nodes=(_node("s_int"), _node("exit", boundary=True)),
        edges=(_edge("e1", "s_int", "exit"),),
    )
    balances = (_bal("s_int", 8.0), _bal("exit", -8.0))

    ods = estimate_od_open(graph, balances, _config())

    assert _require_od(ods, "s_int", "exit").demand == pytest.approx(8.0)
