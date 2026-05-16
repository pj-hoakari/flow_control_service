"""arc_index helper tests (math companion §8.1, §11.2.1)."""

from __future__ import annotations

import pytest

from flow_control.models import (
    DirectionConstraint,
    FlowDirection,
    Graph,
)
from flow_control.optimization import build_arc_index

from tests.conftest import make_edge, make_node


def _graph(*, edge: dict | None = None) -> Graph:
    nodes = (
        make_node("n1", is_boundary=True),
        make_node("n2"),
        make_node("n3", is_boundary=True),
    )
    edges = (
        make_edge("e1", "n1", "n2", **(edge or {})),
        make_edge("e2", "n2", "n3"),
    )
    return Graph(nodes=nodes, edges=edges)


def test_disabled_edge_is_excluded():
    g = _graph(edge={"enabled": False})
    idx = build_arc_index(g)
    assert all(a.edge_id != "e1" for a in idx.arcs)
    assert len(idx.arcs) == 2  # e2 のみ A2B / B2A


def test_disabled_node_excludes_incident_edges():
    nodes = (
        make_node("n1", is_boundary=True),
        make_node("n2", enabled=False),
        make_node("n3", is_boundary=True),
    )
    edges = (
        make_edge("e1", "n1", "n2"),
        make_edge("e2", "n2", "n3"),
    )
    idx = build_arc_index(Graph(nodes=nodes, edges=edges))
    assert idx.arcs == ()  # 全エッジが n2 を端点に持つので消える
    assert idx.nodes_active == ("n1", "n3")
    assert idx.entry_nodes == ("n1", "n3")


def test_bidirectional_prior_alpha_beta():
    g = _graph(edge={"direction_constraint": DirectionConstraint.BIDIRECTIONAL_PRIOR})
    idx = build_arc_index(g)
    a2b, b2a = idx.by_edge["e1"]
    assert (a2b.alpha, a2b.beta) == (1, 0)
    assert (b2a.alpha, b2a.beta) == (1, 0)


def test_legal_fixed_a_to_b_alpha_beta():
    g = _graph(edge={"direction_constraint": DirectionConstraint.LEGAL_FIXED_A_TO_B})
    idx = build_arc_index(g)
    a2b, b2a = idx.by_edge["e1"]
    assert (a2b.alpha, a2b.beta) == (1, 1)
    assert (b2a.alpha, b2a.beta) == (0, 1)


def test_legal_fixed_b_to_a_alpha_beta():
    g = _graph(edge={"direction_constraint": DirectionConstraint.LEGAL_FIXED_B_TO_A})
    idx = build_arc_index(g)
    a2b, b2a = idx.by_edge["e1"]
    assert (a2b.alpha, a2b.beta) == (0, 1)
    assert (b2a.alpha, b2a.beta) == (1, 1)


def test_legal_fixed_bidirectional_alpha_beta():
    g = _graph(edge={"direction_constraint": DirectionConstraint.LEGAL_FIXED_BIDIRECTIONAL})
    idx = build_arc_index(g)
    a2b, b2a = idx.by_edge["e1"]
    assert (a2b.alpha, a2b.beta) == (1, 1)
    assert (b2a.alpha, b2a.beta) == (1, 1)


def test_oneway_prior_treated_as_bidirectional():
    """ONEWAY_*_PRIOR は最適化が変更可能なので両方向許容、固定なし。"""
    g = _graph(edge={"direction_constraint": DirectionConstraint.ONEWAY_A_TO_B_PRIOR})
    idx = build_arc_index(g)
    a2b, b2a = idx.by_edge["e1"]
    assert (a2b.alpha, a2b.beta) == (1, 0)
    assert (b2a.alpha, b2a.beta) == (1, 0)


def test_by_node_in_out_partition(line_graph_3):
    idx = build_arc_index(line_graph_3)
    # n1 から出る → e1#A2B、n1 に入る → e1#B2A
    outs_n1 = {a.arc_id for a in idx.by_node_out["n1"]}
    ins_n1 = {a.arc_id for a in idx.by_node_in["n1"]}
    assert outs_n1 == {"e1#A2B"}
    assert ins_n1 == {"e1#B2A"}
    # n2 (中継): e1#B2A は n1 へ出る、e2#A2B は n3 へ出る
    outs_n2 = {a.arc_id for a in idx.by_node_out["n2"]}
    ins_n2 = {a.arc_id for a in idx.by_node_in["n2"]}
    assert outs_n2 == {"e1#B2A", "e2#A2B"}
    assert ins_n2 == {"e1#A2B", "e2#B2A"}


def test_entry_nodes_sorted(line_graph_3):
    idx = build_arc_index(line_graph_3)
    assert idx.entry_nodes == ("n1", "n3")  # sorted


def test_flow_direction_marked_correctly(line_graph_3):
    idx = build_arc_index(line_graph_3)
    a2b, b2a = idx.by_edge["e1"]
    assert a2b.flow_direction is FlowDirection.A_TO_B
    assert b2a.flow_direction is FlowDirection.B_TO_A
    assert a2b.tail_node_id == "n1" and a2b.head_node_id == "n2"
    assert b2a.tail_node_id == "n2" and b2a.head_node_id == "n1"
