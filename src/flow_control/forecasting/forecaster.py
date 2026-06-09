from dataclasses import dataclass, field

from ..domain.graph import EdgeID, Graph
from ..domain.history import HistoryDigest
from ..domain.observations import Observations
from ..domain.references import Reference
from .config import ResolvedConfig
from .demand import NodeDemand, compute_node_demand
from .od import NodeResolution, ODDemand, estimate_od
from .validation import NodeConfidence, validate_od


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
    estimation_resolution: tuple[NodeResolution, ...] = ()
    reproduction_error: float = 0.0
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

    # Step A: 点需要の独立推定
    node_demand = compute_node_demand(graph, observations, config)

    # Step B: OD 推定
    od_result = estimate_od(
        graph, observations, node_demand, config, is_open_mode=is_open_mode
    )

    # Step C: 整合・検証（再現残差とノード信頼度）
    validation = validate_od(graph, observations, od_result.od_matrix, config)

    arc_flow_sensitivity: tuple[ArcFlowSensitivity, ...] = ()
    fallback_usage = FallbackReport()

    return ForecastResult(
        od_matrix=od_result.od_matrix,
        node_demand=node_demand,
        estimation_resolution=od_result.resolutions,
        reproduction_error=validation.reproduction_error,
        node_confidence=validation.node_confidence,
        arc_flow_sensitivity=arc_flow_sensitivity,
        fallback_usage=fallback_usage,
    )
