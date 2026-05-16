"""Shared model package for the flow control service.

Frozen dataclasses are used so that all module functions can stay pure and
side-effect free.
"""

from .config import ResolvedConfig
from .detection_state import (
    ArcWatchState,
    DetectionState,
    QueuedTrigger,
    RetriggerEntry,
    freeze_map,
    freeze_retrigger_map,
    freeze_watch_map,
)
from .detour import DetourResult, DetourSet, Path
from .diagnostics import TriggerEvidence
from .enums import (
    ConfidenceFlag,
    CurrentDirection,
    DirectionConstraint,
    EventKind,
    FlowDirection,
    NodeKind,
    ObservationType,
    QueuedTriggerKind,
    TargetKind,
    TenantCategory,
    TriggerSource,
    VerdictHint,
)
from .events import Event
from .forecast import (
    Commodity,
    FallbackReport,
    ForecastResult,
    freeze_float_map,
    freeze_int_map,
)
from .graph import Edge, Graph, Node
from .history import ArcHistoryStat, ArcWindowSeries, HistoryDigest
from .observations import (
    ArcFlow,
    ArcScalarFlow,
    ArcStagnation,
    NodeOccupancy,
    Observations,
)
from .optimization import (
    ConstraintReport,
    DirectionProposal,
    ImportanceDirection,
    ObjectiveValues,
    OptimizationResult,
    PhaseStatus,
    ProposedDirection,
    RouteImportance,
    SolverStats,
    SolverStatus,
)
from .reference import Reference, TagReference, ThresholdDefaults, ThresholdSet
from .target_key import make_edge_key, make_node_key, parse_target_key
from .tenant import TenantContext

__all__ = [
    "ArcFlow",
    "ArcHistoryStat",
    "ArcScalarFlow",
    "ArcStagnation",
    "ArcWatchState",
    "ArcWindowSeries",
    "Commodity",
    "ConfidenceFlag",
    "ConstraintReport",
    "CurrentDirection",
    "DetectionState",
    "DetourResult",
    "DetourSet",
    "DirectionConstraint",
    "DirectionProposal",
    "Edge",
    "Event",
    "EventKind",
    "FallbackReport",
    "FlowDirection",
    "ForecastResult",
    "Graph",
    "HistoryDigest",
    "ImportanceDirection",
    "Node",
    "NodeKind",
    "NodeOccupancy",
    "ObjectiveValues",
    "Observations",
    "ObservationType",
    "OptimizationResult",
    "Path",
    "PhaseStatus",
    "ProposedDirection",
    "QueuedTrigger",
    "QueuedTriggerKind",
    "Reference",
    "ResolvedConfig",
    "RetriggerEntry",
    "RouteImportance",
    "SolverStats",
    "SolverStatus",
    "TagReference",
    "TargetKind",
    "TenantCategory",
    "TenantContext",
    "ThresholdDefaults",
    "ThresholdSet",
    "TriggerEvidence",
    "TriggerSource",
    "VerdictHint",
    "freeze_float_map",
    "freeze_int_map",
    "freeze_map",
    "freeze_retrigger_map",
    "freeze_watch_map",
    "make_edge_key",
    "make_node_key",
    "parse_target_key",
]
