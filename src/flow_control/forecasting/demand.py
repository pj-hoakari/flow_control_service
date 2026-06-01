from collections import deque
from dataclasses import dataclass

from ..domain.enums import FlowDirection, ObservationType
from ..domain.graph import Graph, NodeID
from ..domain.observations import ConfidenceFlag, Observations
from .config import ResolvedConfig


@dataclass(frozen=True)
class NodeFlowBalance:
    node_id: NodeID
    gross_outflow: float
    gross_inflow: float

    @property
    def net_demand(self) -> float:
        return self.gross_outflow - self.gross_inflow


@dataclass(frozen=True)
class ODDemand:
    origin: NodeID
    destination: NodeID
    demand: float


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


def _build_adjacency(graph: Graph) -> dict[NodeID, list[NodeID]]:
    """有効エッジから無向隣接リストを構築する

    ホップ距離算出用
    観測型に依らず enabled なエッジを物理ネットワークとして扱う
    """
    enabled_node_ids = {node.node_id for node in graph.enabled_nodes()}
    adjacency: dict[NodeID, list[NodeID]] = {nid: [] for nid in enabled_node_ids}
    for edge in graph.enabled_edges():
        a, b = edge.endpoint_a, edge.endpoint_b
        if a in enabled_node_ids and b in enabled_node_ids:
            adjacency[a].append(b)
            adjacency[b].append(a)
    return adjacency


def _hop_distances(
    adjacency: dict[NodeID, list[NodeID]], source: NodeID
) -> dict[NodeID, int]:
    """source から各ノードへの無向ホップ数を BFS で算出
    到達不能ノードは欠落
    """
    distances: dict[NodeID, int] = {source: 0}
    queue: deque[NodeID] = deque((source,))
    while queue:
        current = queue.popleft()
        for neighbor in adjacency.get(current, ()):
            if neighbor not in distances:
                distances[neighbor] = distances[current] + 1
                queue.append(neighbor)
    return distances


def estimate_od_open(
    graph: Graph,
    node_flow_balances: tuple[NodeFlowBalance, ...],
    config: ResolvedConfig,
) -> tuple[ODDemand, ...]:
    """Open モードの単制約重力モデルで OD 需要 δ_{s,t} を推定

    - 入退出点（境界ノード）を無限容量バッファとみなし，ネット需要 b_v の均等補正は行わない
    - ネット需要 b_v = h_v - g_v から Source S+={v:b_v>0}・Sink S-={v:b_v<0} を構成
    - 重み w_{s,t} = 1/(d_{s,t}+1)^α（d は無向ホップ数，α = config.gravity_alpha）
    - δ_{s,t} = b_s^+ · |b_t^-|·w_{s,t} / Σ_{t'∈S-} |b_{t'}^-|·w_{s,t'}
      （単制約モデル：Source ごとに Σ_t δ_{s,t} = b_s^+ を保証）
    - 外部→外部（境界→境界）は OD 対象外（3 種類のコモディティ：ext→int / int→ext / int→int）
    - δ_{s,t} > config.delta_min のもののみ採用（§10.3 の K）

    戻り値は node_flow_balances（= enabled_nodes() 順）の (source, sink) 順で決定的
    到達可能な Sink が無い Source はスキップする
    """
    boundary_ids = {node.node_id for node in graph.boundary_nodes()}
    sources = tuple(b for b in node_flow_balances if b.net_demand > 0.0)
    sinks = tuple(b for b in node_flow_balances if b.net_demand < 0.0)
    if not sources or not sinks:
        return ()

    adjacency = _build_adjacency(graph)
    alpha = config.gravity_alpha

    od_demands: list[ODDemand] = []
    for source in sources:
        source_is_boundary = source.node_id in boundary_ids
        distances = _hop_distances(adjacency, source.node_id)

        # 当該 Source から到達可能かつ対象となる Sink の重みを算出
        weighted_sinks: list[tuple[NodeFlowBalance, float]] = []
        weight_total = 0.0
        for sink in sinks:
            if source_is_boundary and sink.node_id in boundary_ids:
                continue  # 外部→外部は対象外
            hop = distances.get(sink.node_id)
            if hop is None:
                continue  # 到達不能
            weight = 1.0 / (hop + 1) ** alpha
            contribution = abs(sink.net_demand) * weight
            weighted_sinks.append((sink, contribution))
            weight_total += contribution

        if weight_total <= 0.0:
            continue

        for sink, contribution in weighted_sinks:
            delta = source.net_demand * (contribution / weight_total)
            if delta > config.delta_min:
                od_demands.append(
                    ODDemand(
                        origin=source.node_id,
                        destination=sink.node_id,
                        demand=delta,
                    )
                )

    return tuple(od_demands)
