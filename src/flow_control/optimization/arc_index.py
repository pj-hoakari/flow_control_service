"""Directed arc enumeration and α/β derivation (math companion §8.1, §11.2.1)."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from ..models import (
    DirectionConstraint,
    FlowDirection,
    Graph,
    ObservationType,
)


@dataclass(frozen=True)
class DirectedArc:
    """1 つのエッジに対応する 1 方向アーク。

    `alpha` (α_a) は事前制約上その方向が許容されるかを示す 0/1。
    `beta` (β_a) は法規制等で方向が固定されているかを示す 0/1。β_a=1 のとき
    最適化制約は x_a = α_a を強制する（math companion §11.2.1）。
    """

    arc_id: str
    edge_id: str
    tail_node_id: str
    head_node_id: str
    flow_direction: FlowDirection
    alpha: int
    beta: int
    is_scalar: bool
    danger_capacity: float | None


@dataclass(frozen=True)
class ArcIndex:
    arcs: tuple[DirectedArc, ...]
    by_edge: Mapping[str, tuple[DirectedArc, DirectedArc]]
    by_node_out: Mapping[str, tuple[DirectedArc, ...]]
    by_node_in: Mapping[str, tuple[DirectedArc, ...]]
    nodes_active: tuple[str, ...]
    entry_nodes: tuple[str, ...]

    def arc_by_id(self, arc_id: str) -> DirectedArc | None:
        for a in self.arcs:
            if a.arc_id == arc_id:
                return a
        return None


def _alpha_beta(constraint: DirectionConstraint) -> tuple[tuple[int, int], tuple[int, int]]:
    """`(α_A2B, α_B2A)`, `(β_A2B, β_B2A)` を返す。"""
    match constraint:
        case DirectionConstraint.BIDIRECTIONAL_PRIOR:
            return (1, 1), (0, 0)
        case DirectionConstraint.ONEWAY_A_TO_B_PRIOR:
            # 「事前推奨」は最適化が変更可能。両方向許容、固定なし。
            return (1, 1), (0, 0)
        case DirectionConstraint.ONEWAY_B_TO_A_PRIOR:
            return (1, 1), (0, 0)
        case DirectionConstraint.LEGAL_FIXED_A_TO_B:
            return (1, 0), (1, 1)
        case DirectionConstraint.LEGAL_FIXED_B_TO_A:
            return (0, 1), (1, 1)
        case DirectionConstraint.LEGAL_FIXED_BIDIRECTIONAL:
            return (1, 1), (1, 1)
    raise ValueError(f"unknown direction_constraint: {constraint}")


def build_arc_index(graph: Graph) -> ArcIndex:
    """Graph から有向アーク列を構築。`enabled=False` のエッジ・ノードは除外する。"""
    nodes_active = tuple(sorted(n.node_id for n in graph.nodes if n.enabled))
    entry_nodes = tuple(sorted(n.node_id for n in graph.nodes if n.enabled and n.is_boundary))
    nodes_active_set = set(nodes_active)

    arcs: list[DirectedArc] = []
    by_edge: dict[str, tuple[DirectedArc, DirectedArc]] = {}
    by_out: dict[str, list[DirectedArc]] = {nid: [] for nid in nodes_active}
    by_in: dict[str, list[DirectedArc]] = {nid: [] for nid in nodes_active}

    for edge in graph.edges:
        if not edge.enabled:
            continue
        if edge.endpoint_a not in nodes_active_set or edge.endpoint_b not in nodes_active_set:
            # 端点ノードが無効化されている場合はそのエッジも実効的に無効
            continue

        (alpha_a2b, alpha_b2a), (beta_a2b, beta_b2a) = _alpha_beta(edge.direction_constraint)
        is_scalar = edge.observation_type is ObservationType.SCALAR
        cap = edge.danger_capacity if edge.danger_flag else None

        a2b = DirectedArc(
            arc_id=f"{edge.edge_id}#A2B",
            edge_id=edge.edge_id,
            tail_node_id=edge.endpoint_a,
            head_node_id=edge.endpoint_b,
            flow_direction=FlowDirection.A_TO_B,
            alpha=alpha_a2b,
            beta=beta_a2b,
            is_scalar=is_scalar,
            danger_capacity=cap,
        )
        b2a = DirectedArc(
            arc_id=f"{edge.edge_id}#B2A",
            edge_id=edge.edge_id,
            tail_node_id=edge.endpoint_b,
            head_node_id=edge.endpoint_a,
            flow_direction=FlowDirection.B_TO_A,
            alpha=alpha_b2a,
            beta=beta_b2a,
            is_scalar=is_scalar,
            danger_capacity=cap,
        )
        arcs.extend([a2b, b2a])
        by_edge[edge.edge_id] = (a2b, b2a)
        by_out[edge.endpoint_a].append(a2b)
        by_in[edge.endpoint_b].append(a2b)
        by_out[edge.endpoint_b].append(b2a)
        by_in[edge.endpoint_a].append(b2a)

    return ArcIndex(
        arcs=tuple(arcs),
        by_edge=MappingProxyType(by_edge),
        by_node_out=MappingProxyType({k: tuple(v) for k, v in by_out.items()}),
        by_node_in=MappingProxyType({k: tuple(v) for k, v in by_in.items()}),
        nodes_active=nodes_active,
        entry_nodes=entry_nodes,
    )
