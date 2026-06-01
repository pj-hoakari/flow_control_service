from dataclasses import dataclass

from ..domain.enums import FlowDirection, ObservationType
from ..domain.graph import Graph, NodeID
from ..domain.observations import ConfidenceFlag, Observations


@dataclass(frozen=True)
class NodeFlowBalance:
    node_id: NodeID
    gross_outflow: float
    gross_inflow: float

    @property
    def net_demand(self) -> float:
        return self.gross_outflow - self.gross_inflow


def compute_node_flow_balances(
    graph: Graph,
    observations: Observations,
) -> tuple[NodeFlowBalance, ...]:
    active_nodes = graph.enabled_nodes()
    outflow: dict[NodeID, float] = {node.node_id: 0.0 for node in active_nodes}
    inflow: dict[NodeID, float] = {node.node_id: 0.0 for node in active_nodes}

    for arc_flow in observations.arc_flows:
        if arc_flow.confidence_flag == ConfidenceFlag.INVALID:
            continue
        edge = graph.edge_of(arc_flow.edge_id)
        if edge is None or not edge.enabled:
            continue
        if edge.observation_type != ObservationType.VECTOR:
            continue

        if arc_flow.direction == FlowDirection.A_TO_B:
            source, destination = edge.endpoint_a, edge.endpoint_b
        else:
            source, destination = edge.endpoint_b, edge.endpoint_a

        if source in outflow:
            outflow[source] += arc_flow.flow_rate
        if destination in inflow:
            inflow[destination] += arc_flow.flow_rate

    return tuple(
        NodeFlowBalance(
            node_id=node.node_id,
            gross_outflow=outflow[node.node_id],
            gross_inflow=inflow[node.node_id],
        )
        for node in active_nodes
    )
