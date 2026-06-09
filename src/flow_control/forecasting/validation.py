"""整合・検証

推定 OD（od_matrix）から経路配分でリンク流量を再現し，観測との残差 reproduction_error を算出
残差と観測の信頼度フラグを node_confidence に反映し，Optimization の目的関数重みに供する

    resid = Σ_a |v̂_a − v_a| / (Σ_a v_a + ε_0),   v̂_a = Σ_{s,t} M^{(s,t)}_a δ_{s,t}
"""

from collections import defaultdict, deque
from dataclasses import dataclass

from ..domain.enums import FlowDirection, ObservationType
from ..domain.graph import Graph, NodeID
from ..domain.observations import ConfidenceFlag, Observations
from .config import ResolvedConfig
from .od import ODDemand

# 観測信頼度フラグごとのノード信頼度減衰係数
_HOLD_FACTOR = 0.7
_INVALID_FACTOR = 0.0
# 有効ベクトルアークに観測が無い（欠損）場合：直接計測なしとして INVALID と同等に扱う
_MISSING_FACTOR = 0.0

# 有向アークのキー：(edge_id, from_node)
_ArcKey = tuple[str, NodeID]


@dataclass(frozen=True)
class NodeConfidence:
    node_id: NodeID
    confidence: float  # 0.0-1.0


@dataclass(frozen=True)
class ValidationResult:
    reproduction_error: float = 0.0
    node_confidence: tuple[NodeConfidence, ...] = ()


def validate_od(
    graph: Graph,
    observations: Observations,
    od_matrix: tuple[ODDemand, ...],
    config: ResolvedConfig,
) -> ValidationResult:
    """OD の再現残差とノード信頼度を算出

    - reproduction_error: 推定 OD を最短路配分してリンク流量を再現し，観測との相対残差
    - node_confidence: 再現品質（全体）× 観測信頼度（§5.5：HOLD 0.7・INVALID/欠損 0.0）
    """
    observed = _observed_arc_flows(graph, observations)
    reproduced = _reproduce_arc_flows(graph, od_matrix)
    reproduction_error = _reproduction_error(observed, reproduced, config.epsilon_0)
    node_confidence = _node_confidence(graph, observations, reproduction_error)
    return ValidationResult(
        reproduction_error=reproduction_error,
        node_confidence=node_confidence,
    )


def _observed_arc_flows(
    graph: Graph, observations: Observations
) -> dict[_ArcKey, float]:
    """有効ベクトルアークの観測流量を有向アーク (edge_id, from_node) で集める（INVALID 除外）"""
    flows: dict[_ArcKey, float] = defaultdict(float)
    for arc_flow in observations.arc_flows:
        if arc_flow.confidence_flag == ConfidenceFlag.INVALID:
            continue
        edge = graph.edge_of(arc_flow.edge_id)
        if edge is None or not edge.enabled:
            continue
        if edge.observation_type != ObservationType.VECTOR:
            continue
        from_node = (
            edge.endpoint_a
            if arc_flow.direction == FlowDirection.A_TO_B
            else edge.endpoint_b
        )
        flows[(edge.edge_id.value, from_node)] += arc_flow.flow_rate
    return dict(flows)


def _reproduce_arc_flows(
    graph: Graph, od_matrix: tuple[ODDemand, ...]
) -> dict[_ArcKey, float]:
    """各 OD 需要を最短路に配分してリンク流量 v̂_a を再現"""
    adjacency = _build_adjacency(graph)
    reproduced: dict[_ArcKey, float] = defaultdict(float)
    for od in od_matrix:
        arcs = _shortest_path_arcs(adjacency, od.origin, od.destination)
        if arcs is None:
            continue  # 到達不能な OD は配分対象外
        for key in arcs:
            reproduced[key] += od.demand
    return dict(reproduced)


def _reproduction_error(
    observed: dict[_ArcKey, float],
    reproduced: dict[_ArcKey, float],
    epsilon_0: float,
) -> float:
    """相対再現残差 Σ|v̂−v| / (Σv + ε_0) を算出"""
    total_observed = sum(observed.values())
    keys = set(observed) | set(reproduced)
    abs_error = sum(
        abs(reproduced.get(key, 0.0) - observed.get(key, 0.0)) for key in keys
    )
    if total_observed <= 0.0:
        # 検証対象のリンク観測が無い：再現すべき OD も無ければ残差 0，あれば検証不能として最大
        return 0.0 if not reproduced else 1.0
    return abs_error / (total_observed + epsilon_0)


def _node_confidence(
    graph: Graph,
    observations: Observations,
    reproduction_error: float,
) -> tuple[NodeConfidence, ...]:
    """再現品質（全体）と観測信頼度から各ノードの信頼度を決める

    confidence_v = base × min(接続する有効ベクトルアークの信頼度係数)
    base = clamp(1 − reproduction_error, 0, 1)
    """
    base = max(0.0, min(1.0, 1.0 - reproduction_error))

    flag_by_edge: dict[str, ConfidenceFlag] = {}
    for arc_flow in observations.arc_flows:
        # 同一エッジに複数観測があれば最も低信頼（INVALID > HOLD > OK）を採る
        current = flag_by_edge.get(arc_flow.edge_id.value)
        flag_by_edge[arc_flow.edge_id.value] = _worse_flag(
            current, arc_flow.confidence_flag
        )

    incident: dict[NodeID, list[str]] = defaultdict(list)
    for edge in graph.enabled_edges():
        if edge.observation_type != ObservationType.VECTOR:
            continue
        incident[edge.endpoint_a].append(edge.edge_id.value)
        incident[edge.endpoint_b].append(edge.edge_id.value)

    result: list[NodeConfidence] = []
    for node in graph.enabled_nodes():
        factor = 1.0
        for edge_id in incident.get(node.node_id, ()):
            factor = min(factor, _arc_factor(flag_by_edge.get(edge_id)))
        result.append(NodeConfidence(node_id=node.node_id, confidence=base * factor))
    return tuple(result)


def _arc_factor(flag: ConfidenceFlag | None) -> float:
    """観測信頼度フラグ → ノード信頼度減衰係数
    観測欠損（None）は計測なし扱い
    """
    if flag is None:
        return _MISSING_FACTOR
    if flag == ConfidenceFlag.INVALID:
        return _INVALID_FACTOR
    if flag == ConfidenceFlag.HOLD:
        return _HOLD_FACTOR
    return 1.0


def _worse_flag(
    current: ConfidenceFlag | None, candidate: ConfidenceFlag
) -> ConfidenceFlag:
    """より低信頼なフラグを返す（INVALID < HOLD < OK）"""
    order = {ConfidenceFlag.INVALID: 0, ConfidenceFlag.HOLD: 1, ConfidenceFlag.OK: 2}
    if current is None:
        return candidate
    return current if order[current] <= order[candidate] else candidate


def _build_adjacency(graph: Graph) -> dict[NodeID, list[tuple[NodeID, str]]]:
    """有効エッジから (隣接ノード, edge_id) の無向隣接リストを構築"""
    enabled_node_ids = {node.node_id for node in graph.enabled_nodes()}
    adjacency: dict[NodeID, list[tuple[NodeID, str]]] = {
        nid: [] for nid in enabled_node_ids
    }
    for edge in graph.enabled_edges():
        a, b = edge.endpoint_a, edge.endpoint_b
        if a in enabled_node_ids and b in enabled_node_ids:
            adjacency[a].append((b, edge.edge_id.value))
            adjacency[b].append((a, edge.edge_id.value))
    return adjacency


def _shortest_path_arcs(
    adjacency: dict[NodeID, list[tuple[NodeID, str]]],
    source: NodeID,
    target: NodeID,
) -> list[_ArcKey] | None:
    """source→target の単一最短路を有向アーク (edge_id, from_node) 列で返す（BFS，決定的）

    到達不能なら None。source == target は空列
    """
    if source == target:
        return []
    visited = {source}
    parent: dict[NodeID, tuple[NodeID, str]] = {}
    queue: deque[NodeID] = deque((source,))
    while queue:
        current = queue.popleft()
        for neighbor, edge_id in adjacency.get(current, ()):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            parent[neighbor] = (current, edge_id)
            if neighbor == target:
                return _reconstruct(parent, source, target)
            queue.append(neighbor)
    return None


def _reconstruct(
    parent: dict[NodeID, tuple[NodeID, str]], source: NodeID, target: NodeID
) -> list[_ArcKey]:
    arcs: list[_ArcKey] = []
    node = target
    while node != source:
        prev, edge_id = parent[node]
        arcs.append((edge_id, prev))  # prev からの有向アーク
        node = prev
    arcs.reverse()
    return arcs
