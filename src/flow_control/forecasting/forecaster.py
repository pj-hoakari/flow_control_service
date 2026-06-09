from dataclasses import dataclass, field

from ..domain.graph import EdgeID, Graph, NodeID
from ..domain.history import HistoryDigest
from ..domain.observations import Observations
from ..domain.references import Reference
from .config import ResolvedConfig
from .demand import NodeDemand, ODDemand, compute_node_demand, estimate_od_open


@dataclass(frozen=True)
class NodeConfidence:
    node_id: NodeID
    confidence: float


@dataclass(frozen=True)
class ArcFlowSensitivity:
    edge_id: EdgeID
    eta: float


@dataclass(frozen=True)
class ReferenceSampleCount:
    attribute_tag: str
    sample_count: int


@dataclass(frozen=True)
class FallbackReport:
    used_reference_edges: tuple[EdgeID, ...] = ()
    used_default_edges: tuple[EdgeID, ...] = ()
    reference_sample_counts: tuple[ReferenceSampleCount, ...] = ()


@dataclass(frozen=True)
class ForecastResult:
    od_matrix: tuple[ODDemand, ...] = ()
    node_demand: tuple[NodeDemand, ...] = ()
    node_confidence: tuple[NodeConfidence, ...] = ()
    arc_flow_sensitivity: tuple[ArcFlowSensitivity, ...] = ()
    fallback_usage: FallbackReport = field(default_factory=FallbackReport)


def forecast(
    graph: Graph,
    observations: Observations,
    history_digest: HistoryDigest,
    references: Reference,
    triggered_edges: tuple[EdgeID, ...],
    config: ResolvedConfig,
) -> ForecastResult:
    is_open_mode = len(graph.boundary_nodes()) > 0

    # Step A: 点需要の独立推定（モード非依存，数理補助 §10.1）
    node_demand = compute_node_demand(graph, observations, config)

    # Step B: OD 推定（数理補助 §10.2）
    if is_open_mode:
        od_matrix = estimate_od_open(graph, node_demand, config)
    else:
        # TODO: Closed モードの両制約 IPF
        od_matrix = ()

    arc_flow_sensitivity: tuple[ArcFlowSensitivity, ...] = ()
    fallback_usage = FallbackReport()

    node_confidence: tuple[NodeConfidence, ...] = ()

    return ForecastResult(
        od_matrix=od_matrix,
        node_demand=node_demand,
        node_confidence=node_confidence,
        arc_flow_sensitivity=arc_flow_sensitivity,
        fallback_usage=fallback_usage,
    )
