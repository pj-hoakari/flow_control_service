"""Direction proposal extraction tests (math companion §11.2.1)."""

from __future__ import annotations

import pytest

from flow_control.models import (
    ArcStagnation,
    DirectionConstraint,
    Graph,
    ProposedDirection,
)
from flow_control.optimization import build_arc_index, optimize

from tests.conftest import (
    make_edge,
    make_forecast_result,
    make_commodity,
    make_node,
    make_observations,
    make_detour_result,
)


def _proposal_for(result, edge_id: str) -> ProposedDirection:
    for dp in result.optimization_result.direction_proposal:
        if dp.edge_id == edge_id:
            return dp.proposed_direction
    raise AssertionError(f"edge {edge_id} not in direction_proposal")


def _triangle_graph(*, e1_constraint=DirectionConstraint.LEGAL_FIXED_A_TO_B) -> Graph:
    """n1 (boundary) と n3 (boundary) を直接結ぶ三角形。ローカル可達性を満たす。"""
    nodes = (
        make_node("n1", is_boundary=True),
        make_node("n2"),
        make_node("n3", is_boundary=True),
    )
    edges = (
        make_edge("e1", "n1", "n2", direction_constraint=e1_constraint),
        make_edge("e2", "n2", "n3"),
        make_edge("e3", "n1", "n3"),
    )
    return Graph(nodes=nodes, edges=edges)


def _triangle_obs_and_forecast(base_time):
    obs = make_observations(
        observed_at=base_time,
        arc_stagnations=(
            ArcStagnation("e1", 5.0),
            ArcStagnation("e2", 5.0),
            ArcStagnation("e3", 5.0),
        ),
    )
    forecast = make_forecast_result(
        commodities=(make_commodity("n1", "n3", 1.0),),
        arc_flow_sensitivity={"e1": 1.0, "e2": 1.0, "e3": 1.0},
        arc_baseline_stagnation={"e1": 5.0, "e2": 5.0, "e3": 5.0},
    )
    return obs, forecast


def test_legal_fixed_a_to_b_proposed_as_a_to_b(base_time, baseline_config):
    graph = _triangle_graph(e1_constraint=DirectionConstraint.LEGAL_FIXED_A_TO_B)
    obs, forecast = _triangle_obs_and_forecast(base_time)
    r = optimize(
        graph=graph,
        observations=obs,
        forecast_result=forecast,
        detour_result=make_detour_result(),
        previous_result=None,
        config=baseline_config,
        seed=1,
        server_time=base_time,
    )
    assert _proposal_for(r, "e1") is ProposedDirection.A_TO_B


def test_legal_fixed_b_to_a_proposed_as_b_to_a(base_time, baseline_config):
    nodes = (
        make_node("n1", is_boundary=True),
        make_node("n2"),
        make_node("n3", is_boundary=True),
    )
    edges = (
        # e1 を法規制で B→A 固定 (n1 へ向かう一方向)
        # n3 から n1 への需要を組むため、別経路 e2 を確保
        make_edge("e1", "n2", "n1", direction_constraint=DirectionConstraint.LEGAL_FIXED_B_TO_A),
        make_edge("e2", "n2", "n3"),
        make_edge("e3", "n1", "n3"),
    )
    graph = Graph(nodes=nodes, edges=edges)
    obs = make_observations(
        observed_at=base_time,
        arc_stagnations=(
            ArcStagnation("e1", 5.0),
            ArcStagnation("e2", 5.0),
            ArcStagnation("e3", 5.0),
        ),
    )
    forecast = make_forecast_result(
        commodities=(make_commodity("n1", "n3", 1.0),),
        arc_flow_sensitivity={"e1": 1.0, "e2": 1.0, "e3": 1.0},
        arc_baseline_stagnation={"e1": 5.0, "e2": 5.0, "e3": 5.0},
    )
    r = optimize(
        graph=graph,
        observations=obs,
        forecast_result=forecast,
        detour_result=make_detour_result(),
        previous_result=None,
        config=baseline_config,
        seed=1,
        server_time=base_time,
    )
    # e1 は endpoint_a=n2, endpoint_b=n1。LEGAL_FIXED_B_TO_A は α=(0,1) なので
    # B→A 方向のみ有効 = n1 → n2 の向き。提案は B_TO_A。
    assert _proposal_for(r, "e1") is ProposedDirection.B_TO_A


def test_legal_fixed_bidirectional_proposed_as_bidirectional(base_time, baseline_config, line_graph_3,
                                                              baseline_observations, baseline_forecast,
                                                              empty_detour):
    # line_graph_3 の e1 を LEGAL_FIXED_BIDIRECTIONAL 化
    new_edges = (
        make_edge("e1", "n1", "n2", direction_constraint=DirectionConstraint.LEGAL_FIXED_BIDIRECTIONAL),
        line_graph_3.edges[1],
    )
    graph = Graph(nodes=line_graph_3.nodes, edges=new_edges)
    r = optimize(
        graph=graph,
        observations=baseline_observations,
        forecast_result=baseline_forecast,
        detour_result=empty_detour,
        previous_result=None,
        config=baseline_config,
        seed=1,
        server_time=base_time,
    )
    assert _proposal_for(r, "e1") is ProposedDirection.BIDIRECTIONAL


def test_local_reachability_holds_after_solve(line_graph_3, baseline_observations, baseline_forecast,
                                                 empty_detour, baseline_config, base_time):
    """各 active ノードに対し、提案された方向の入出力アークがそれぞれ最低 1 本ある。"""
    r = optimize(
        graph=line_graph_3,
        observations=baseline_observations,
        forecast_result=baseline_forecast,
        detour_result=empty_detour,
        previous_result=None,
        config=baseline_config,
        seed=1,
        server_time=base_time,
    )
    arc_index = build_arc_index(line_graph_3)
    proposals = {dp.edge_id: dp.proposed_direction for dp in r.optimization_result.direction_proposal}

    def arc_is_active(arc) -> bool:
        p = proposals[arc.edge_id]
        if p is ProposedDirection.BIDIRECTIONAL:
            return True
        if p is ProposedDirection.A_TO_B:
            return arc.arc_id.endswith("#A2B")
        if p is ProposedDirection.B_TO_A:
            return arc.arc_id.endswith("#B2A")
        return False

    for node_id in arc_index.nodes_active:
        out_active = any(arc_is_active(a) for a in arc_index.by_node_out[node_id])
        in_active = any(arc_is_active(a) for a in arc_index.by_node_in[node_id])
        assert out_active, f"node {node_id} has no outgoing active arc"
        assert in_active, f"node {node_id} has no incoming active arc"


def test_alpha_zero_arc_blocked_in_proposal(base_time, baseline_config):
    """LEGAL_FIXED_A_TO_B では B→A 方向の α=0 のため、その方向は importance=0 / direction=NONE。"""
    graph = _triangle_graph(e1_constraint=DirectionConstraint.LEGAL_FIXED_A_TO_B)
    obs, forecast = _triangle_obs_and_forecast(base_time)
    r = optimize(
        graph=graph, observations=obs, forecast_result=forecast,
        detour_result=make_detour_result(), previous_result=None,
        config=baseline_config, seed=1, server_time=base_time,
    )
    # e1 の B_TO_A 方向の importance 行は NONE / 0
    e1_rows = [ri for ri in r.optimization_result.route_importance if ri.edge_id == "e1"]
    assert len(e1_rows) == 2
    b2a_row = next(ri for ri in e1_rows if ri.direction.value in ("B_TO_A", "NONE"))
    # x が 0 になるため NONE 化される
    assert b2a_row.importance == 0.0
