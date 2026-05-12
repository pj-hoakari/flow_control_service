"""Graph model (module design v1 §3.3)."""

from __future__ import annotations

from dataclasses import dataclass, field

from .enums import CurrentDirection, DirectionConstraint, NodeKind, ObservationType


@dataclass(frozen=True)
class Node:
    node_id: str
    kind: NodeKind
    is_boundary: bool
    enabled: bool
    attribute_tags: tuple[str, ...] = ()
    occupancy_score: float = 0.0
    time_resolution_s: int = 60


@dataclass(frozen=True)
class Edge:
    edge_id: str
    endpoint_a: str
    endpoint_b: str
    direction_constraint: DirectionConstraint
    current_direction: CurrentDirection
    enabled: bool
    observation_type: ObservationType
    attribute_tags: tuple[str, ...] = ()
    time_resolution_s: int = 60
    danger_flag: bool = False
    danger_capacity: float | None = None


@dataclass(frozen=True)
class Graph:
    nodes: tuple[Node, ...] = field(default_factory=tuple)
    edges: tuple[Edge, ...] = field(default_factory=tuple)

    def node_by_id(self, node_id: str) -> Node | None:
        for n in self.nodes:
            if n.node_id == node_id:
                return n
        return None

    def edge_by_id(self, edge_id: str) -> Edge | None:
        for e in self.edges:
            if e.edge_id == edge_id:
                return e
        return None
