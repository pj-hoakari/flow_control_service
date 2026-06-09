"""ルート需要（OD）の推定

点需要分解の周辺量（prod_v / absorb_v）と観測のアーク流量を入力に，OD 需要行列 δ_{s,t} を推定

- TURNING_EXACT   : 全ノードが決定可能（単入口/単出口）かつ全アーク観測済み → 転換率の前方伝播
- DOUBLY_CONSTRAINED: 合流＋分岐ノードを含む → 両制約 IPF（Furness 法）＋距離 prior
- DISTANCE_PRIOR  : 流量観測が無い（占有のみ） → 距離 prior による純再配分
"""

from collections import defaultdict, deque
from dataclasses import dataclass
from enum import Enum

from ..domain.enums import FlowDirection, NodeKind, ObservationType
from ..domain.graph import EdgeID, Graph, Node, NodeID
from ..domain.observations import ConfidenceFlag, Observations
from .config import ResolvedConfig
from .demand import NodeDemand

# 前方伝播の伝播ステップ上限（純通過サイクルの無限ループ防止。1 ステップ = 1 ホップ）
_MAX_PROPAGATION_STEPS = 1000


class ODResolutionMode(str, Enum):
    TURNING_EXACT = "TURNING_EXACT"
    DOUBLY_CONSTRAINED = "DOUBLY_CONSTRAINED"
    DISTANCE_PRIOR = "DISTANCE_PRIOR"


class ODResolutionReason(str, Enum):
    DETERMINED = "DETERMINED"  # 単入口/単出口で転換率を導出可
    MERGE_SPLIT_AMBIGUOUS = (
        "MERGE_SPLIT_AMBIGUOUS"  # 合流＋分岐で不定（追加観測の優先対象）
    )
    SPARSE_OBSERVATION = "SPARSE_OBSERVATION"  # 流量が一部欠測
    NODE_ONLY = "NODE_ONLY"  # 通路観測なし・占有のみ


@dataclass(frozen=True)
class ODDemand:
    origin: NodeID
    destination: NodeID
    demand: float


@dataclass(frozen=True)
class NodeResolution:
    node_id: NodeID
    mode: ODResolutionMode
    reason: ODResolutionReason
    imputed_arcs: tuple[EdgeID, ...] = ()  # 保存補完で復元したアーク


@dataclass(frozen=True)
class ODResult:
    od_matrix: tuple[ODDemand, ...] = ()
    resolutions: tuple[NodeResolution, ...] = ()


@dataclass(frozen=True)
class _DirectedFlow:
    source: NodeID
    destination: NodeID
    rate: float


def estimate_od(
    graph: Graph,
    observations: Observations,
    node_demands: tuple[NodeDemand, ...],
    config: ResolvedConfig,
    *,
    is_open_mode: bool,
) -> ODResult:
    """観測と点需要から OD 需要行列を推定する

    解像度で機構を切替：
    - 全ノード決定可能＋全アーク観測 → 前方伝播（TURNING_EXACT）
    - それ以外で流量観測あり → 両制約 IPF（DOUBLY_CONSTRAINED）
    - 流量観測なし → 距離 prior（DISTANCE_PRIOR）

    OD 採用ペアは δ_{s,t} > config.delta_min のみ
    出力は (origin, destination) 順で決定的
    """
    active_nodes = graph.enabled_nodes()
    boundary_ids = {node.node_id for node in graph.boundary_nodes()}
    flows = _directed_flows(graph, observations)
    has_flow = len(flows) > 0

    in_count, out_count = _io_counts(active_nodes, flows)
    missing_by_node = _missing_observation_by_node(graph, flows)

    resolutions = _build_resolutions(
        active_nodes,
        in_count,
        out_count,
        missing_by_node,
        has_flow=has_flow,
    )

    # 生成源・吸収先の周辺量
    production = {d.node_id: d.production for d in node_demands if d.production > 0.0}
    absorption = {d.node_id: d.absorption for d in node_demands if d.absorption > 0.0}
    if not production or not absorption:
        return ODResult(od_matrix=(), resolutions=resolutions)

    forward_ok = (
        has_flow
        and not any(missing_by_node.values())
        and all(
            _is_decidable(node, in_count[node.node_id], out_count[node.node_id])
            for node in active_nodes
        )
    )

    if forward_ok:
        raw = _forward_propagate(node_demands, production, flows, config)
        raw = _exclude_invalid_pairs(raw, boundary_ids, is_open_mode)
        od = _cut_and_renormalize(raw, config.delta_min, _row_sums(raw))
    else:
        if not is_open_mode:
            _equalize_per_component(production, absorption, graph)
        raw = _ipf(
            graph,
            production,
            absorption,
            boundary_ids,
            config,
            is_open_mode=is_open_mode,
        )
        od = _cut_and_renormalize(raw, config.delta_min, production)

    od_matrix = _to_od_matrix(od, node_demands)
    return ODResult(od_matrix=od_matrix, resolutions=resolutions)


def _directed_flows(
    graph: Graph, observations: Observations
) -> dict[str, _DirectedFlow]:
    """有効ベクトルアークの観測流量を有向（source→destination）で取り出す"""
    flows: dict[str, _DirectedFlow] = {}
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
        flows[edge.edge_id.value] = _DirectedFlow(
            source, destination, arc_flow.flow_rate
        )
    return flows


def _io_counts(
    active_nodes: tuple[Node, ...],
    flows: dict[str, _DirectedFlow],
) -> tuple[dict[NodeID, int], dict[NodeID, int]]:
    """各ノードの観測入口エッジ数 d_in・出口エッジ数 d_out を数える"""
    in_count: dict[NodeID, int] = {node.node_id: 0 for node in active_nodes}
    out_count: dict[NodeID, int] = {node.node_id: 0 for node in active_nodes}
    for flow in flows.values():
        if flow.source in out_count:
            out_count[flow.source] += 1
        if flow.destination in in_count:
            in_count[flow.destination] += 1
    return in_count, out_count


def _missing_observation_by_node(
    graph: Graph, flows: dict[str, _DirectedFlow]
) -> dict[NodeID, bool]:
    """各ノードに観測欠落の有効ベクトルアークが接続しているか"""
    missing: dict[NodeID, bool] = {
        node.node_id: False for node in graph.enabled_nodes()
    }
    for edge in graph.enabled_edges():
        if edge.observation_type != ObservationType.VECTOR:
            continue
        if edge.edge_id.value in flows:
            continue
        if edge.endpoint_a in missing:
            missing[edge.endpoint_a] = True
        if edge.endpoint_b in missing:
            missing[edge.endpoint_b] = True
    return missing


def _is_decidable(node: Node, in_degree: int, out_degree: int) -> bool:
    """転換率が周辺量だけで一意に定まる（DOF=0）か

    d_out^+ = 出口エッジ数 +（滞在可能 kind なら 1）
    GOAL は全到着終端で実質単一出口
    """
    if node.kind == NodeKind.GOAL:
        d_out_plus = 1
    elif node.kind == NodeKind.GOAL_TRANSIT_MIXED:
        d_out_plus = out_degree + 1
    else:  # TRANSIT_ONLY は滞在を出口に数えない
        d_out_plus = out_degree
    return in_degree <= 1 or d_out_plus <= 1


def _build_resolutions(
    active_nodes: tuple[Node, ...],
    in_count: dict[NodeID, int],
    out_count: dict[NodeID, int],
    missing_by_node: dict[NodeID, bool],
    *,
    has_flow: bool,
) -> tuple[NodeResolution, ...]:
    """点／区間ごとの解像度"""
    forward_ok = (
        has_flow
        and not any(missing_by_node.values())
        and all(
            _is_decidable(node, in_count[node.node_id], out_count[node.node_id])
            for node in active_nodes
        )
    )

    resolutions: list[NodeResolution] = []
    for node in active_nodes:
        if not has_flow:
            mode, reason = ODResolutionMode.DISTANCE_PRIOR, ODResolutionReason.NODE_ONLY
        elif forward_ok:
            mode = ODResolutionMode.TURNING_EXACT
            reason = ODResolutionReason.DETERMINED
        else:
            mode = ODResolutionMode.DOUBLY_CONSTRAINED
            if missing_by_node[node.node_id]:
                reason = ODResolutionReason.SPARSE_OBSERVATION
            elif not _is_decidable(
                node, in_count[node.node_id], out_count[node.node_id]
            ):
                reason = ODResolutionReason.MERGE_SPLIT_AMBIGUOUS
            else:
                reason = ODResolutionReason.DETERMINED
        resolutions.append(
            NodeResolution(node_id=node.node_id, mode=mode, reason=reason)
        )
    return tuple(resolutions)


def _forward_propagate(
    node_demands: tuple[NodeDemand, ...],
    production: dict[NodeID, float],
    flows: dict[str, _DirectedFlow],
    config: ResolvedConfig,
) -> dict[tuple[NodeID, NodeID], float]:
    """転換率の前方伝播で OD を直接同定

    各生成源 s の prod_s を seed に，各ノードで終端割合 ρ_v = stay_v/A_v を吸収し，
    残りを出口エッジへ観測流量比で配分して下流へ伝播する
    `A→B`（B で終端）と `A→（B→）C`（B を通過）が厳密に分離される
    """
    gross_in = {d.node_id: d.gross_in for d in node_demands}
    staying = {d.node_id: d.staying for d in node_demands}
    # 終端割合 ρ_v = stay_v/A_v。stay>A の異常時も relay が負にならないよう [0,1] にクランプ
    rho = {
        nid: (min(1.0, staying[nid] / gross_in[nid]) if gross_in[nid] > 0.0 else 0.0)
        for nid in gross_in
    }
    out_split = _out_split(flows)
    tol = config.ipf_tolerance

    od: dict[tuple[NodeID, NodeID], float] = defaultdict(float)
    for source in node_demands:
        if source.node_id not in production:
            continue
        # 生成量を出口エッジへ射出（生成は s で終端しない）
        pending: dict[NodeID, float] = defaultdict(float)
        for neighbor, share in out_split.get(source.node_id, ()):
            pending[neighbor] += source.production * share

        absorbed: dict[NodeID, float] = defaultdict(float)
        steps = 0
        while pending and steps < _MAX_PROPAGATION_STEPS:
            steps += 1
            nxt: dict[NodeID, float] = defaultdict(float)
            moving = 0.0
            for node_id, amount in pending.items():
                ratio = rho.get(node_id, 0.0)
                absorbed[node_id] += ratio * amount
                relay = (1.0 - ratio) * amount
                if relay <= tol:
                    continue
                for neighbor, share in out_split.get(node_id, ()):
                    nxt[neighbor] += relay * share
                    moving += relay * share
            pending = {k: v for k, v in nxt.items() if v > tol}
            if moving <= tol:
                break

        for dest, amount in absorbed.items():
            if amount > 0.0 and dest != source.node_id:
                od[(source.node_id, dest)] += amount

    return dict(od)


def _out_split(
    flows: dict[str, _DirectedFlow],
) -> dict[NodeID, tuple[tuple[NodeID, float], ...]]:
    """各ノードの出口エッジ流量比 q_v[a] = v_a / P_v"""
    out_edges: dict[NodeID, list[tuple[NodeID, float]]] = defaultdict(list)
    out_total: dict[NodeID, float] = defaultdict(float)
    for flow in flows.values():
        out_edges[flow.source].append((flow.destination, flow.rate))
        out_total[flow.source] += flow.rate
    split: dict[NodeID, tuple[tuple[NodeID, float], ...]] = {}
    for node_id, edges in out_edges.items():
        total = out_total[node_id]
        if total <= 0.0:
            continue
        split[node_id] = tuple((dst, rate / total) for dst, rate in edges)
    return split


def _ipf(
    graph: Graph,
    production: dict[NodeID, float],
    absorption: dict[NodeID, float],
    boundary_ids: set[NodeID],
    config: ResolvedConfig,
    *,
    is_open_mode: bool,
) -> dict[tuple[NodeID, NodeID], float]:
    """距離 prior を初期解とする Furness 法（IPF）で行・列周辺へ反復収束

    行制約 Σ_t δ = prod_s，列制約 Σ_s δ = absorb_t
    Open モードは ext→ext を除外
    到達不能ペア（成分横断含む）は対象外
    """
    adjacency = _build_adjacency(graph)
    alpha = config.gravity_alpha

    # 距離 prior を初期重みとして有効ペアを構成
    matrix: dict[tuple[NodeID, NodeID], float] = {}
    for s in production:
        distances = _hop_distances(adjacency, s)
        s_is_boundary = s in boundary_ids
        for t in absorption:
            if t == s:
                continue
            if is_open_mode and s_is_boundary and t in boundary_ids:
                continue  # ext→ext は対象外
            hop = distances.get(t)
            if hop is None:
                continue  # 到達不能（弱連結成分横断を含む）
            matrix[(s, t)] = 1.0 / (hop + 1) ** alpha

    if not matrix:
        return {}

    for _ in range(config.ipf_max_iter):
        max_delta = 0.0
        # 行スケーリング（生成制約）
        row_sum: dict[NodeID, float] = defaultdict(float)
        for (s, _t), value in matrix.items():
            row_sum[s] += value
        for key in matrix:
            s = key[0]
            if row_sum[s] > 0.0:
                scaled = matrix[key] * production[s] / row_sum[s]
                max_delta = max(max_delta, abs(scaled - matrix[key]))
                matrix[key] = scaled
        # 列スケーリング（吸収制約）
        col_sum: dict[NodeID, float] = defaultdict(float)
        for (_s, t), value in matrix.items():
            col_sum[t] += value
        for key in matrix:
            t = key[1]
            if col_sum[t] > 0.0:
                scaled = matrix[key] * absorption[t] / col_sum[t]
                max_delta = max(max_delta, abs(scaled - matrix[key]))
                matrix[key] = scaled
        if max_delta < config.ipf_tolerance:
            break

    # 生成制約を最終的に満たす（Open モードでは境界が列の不均衡を吸収）
    row_sum = defaultdict(float)
    for (s, _t), value in matrix.items():
        row_sum[s] += value
    for key in matrix:
        s = key[0]
        if row_sum[s] > 0.0:
            matrix[key] = matrix[key] * production[s] / row_sum[s]

    return matrix


def _equalize_per_component(
    production: dict[NodeID, float],
    absorption: dict[NodeID, float],
    graph: Graph,
) -> None:
    """Closed モードの均等補正

    弱連結成分ごとに生成・吸収総量を共通量 T=½(Σprod+Σabsorb) へ比例スケールする（in-place）
    """
    for component in _weakly_connected_components(graph):
        prod_total = sum(production.get(nid, 0.0) for nid in component)
        absorb_total = sum(absorption.get(nid, 0.0) for nid in component)
        if prod_total <= 0.0 or absorb_total <= 0.0:
            continue
        target = 0.5 * (prod_total + absorb_total)
        for nid in component:
            if nid in production:
                production[nid] *= target / prod_total
            if nid in absorption:
                absorption[nid] *= target / absorb_total


def _build_adjacency(graph: Graph) -> dict[NodeID, list[NodeID]]:
    """有効エッジから無向隣接リストを構築（ホップ距離・成分算出用）"""
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
    """source から各ノードへの無向ホップ数を BFS で算出（到達不能ノードは欠落）"""
    distances: dict[NodeID, int] = {source: 0}
    queue: deque[NodeID] = deque((source,))
    while queue:
        current = queue.popleft()
        for neighbor in adjacency.get(current, ()):
            if neighbor not in distances:
                distances[neighbor] = distances[current] + 1
                queue.append(neighbor)
    return distances


def _weakly_connected_components(graph: Graph) -> list[set[NodeID]]:
    """有効ノードの弱連結成分（無向）"""
    adjacency = _build_adjacency(graph)
    seen: set[NodeID] = set()
    components: list[set[NodeID]] = []
    for node in graph.enabled_nodes():
        if node.node_id in seen:
            continue
        component: set[NodeID] = set()
        queue: deque[NodeID] = deque((node.node_id,))
        seen.add(node.node_id)
        while queue:
            current = queue.popleft()
            component.add(current)
            for neighbor in adjacency.get(current, ()):
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        components.append(component)
    return components


def _exclude_invalid_pairs(
    od: dict[tuple[NodeID, NodeID], float],
    boundary_ids: set[NodeID],
    is_open_mode: bool,
) -> dict[tuple[NodeID, NodeID], float]:
    """自己 OD と Open モードの ext→ext を除外"""
    result: dict[tuple[NodeID, NodeID], float] = {}
    for (s, t), value in od.items():
        if s == t:
            continue
        if is_open_mode and s in boundary_ids and t in boundary_ids:
            continue
        result[(s, t)] = value
    return result


def _row_sums(
    od: dict[tuple[NodeID, NodeID], float],
) -> dict[NodeID, float]:
    row_sum: dict[NodeID, float] = defaultdict(float)
    for (s, _t), value in od.items():
        row_sum[s] += value
    return dict(row_sum)


def _cut_and_renormalize(
    od: dict[tuple[NodeID, NodeID], float],
    delta_min: float,
    row_target: dict[NodeID, float],
) -> dict[tuple[NodeID, NodeID], float]:
    """δ_{s,t} > δ_min のみ採用し，残った要素で行周辺を再正規化"""
    kept = {key: value for key, value in od.items() if value > delta_min}
    row_sum: dict[NodeID, float] = defaultdict(float)
    for (s, _t), value in kept.items():
        row_sum[s] += value
    result: dict[tuple[NodeID, NodeID], float] = {}
    for key, value in kept.items():
        s = key[0]
        target = row_target.get(s, 0.0)
        if row_sum[s] > 0.0 and target > 0.0:
            result[key] = value * target / row_sum[s]
        else:
            result[key] = value
    return result


def _to_od_matrix(
    od: dict[tuple[NodeID, NodeID], float],
    node_demands: tuple[NodeDemand, ...],
) -> tuple[ODDemand, ...]:
    """(origin, destination) を node_demands 順に並べた決定的な ODDemand 列"""
    order = [d.node_id for d in node_demands]
    matrix: list[ODDemand] = []
    for origin in order:
        for destination in order:
            value = od.get((origin, destination))
            if value is not None:
                matrix.append(
                    ODDemand(origin=origin, destination=destination, demand=value)
                )
    return tuple(matrix)
