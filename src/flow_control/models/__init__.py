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
from .graph import Edge, Graph, Node
from .history import ArcHistoryStat, ArcWindowSeries, HistoryDigest
from .observations import (
    ArcFlow,
    ArcScalarFlow,
    ArcStagnation,
    NodeOccupancy,
    Observations,
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
    "ConfidenceFlag",
    "CurrentDirection",
    "DetectionState",
    "DirectionConstraint",
    "Edge",
    "Event",
    "EventKind",
    "FlowDirection",
    "Graph",
    "HistoryDigest",
    "Node",
    "NodeKind",
    "NodeOccupancy",
    "Observations",
    "ObservationType",
    "QueuedTrigger",
    "QueuedTriggerKind",
    "Reference",
    "ResolvedConfig",
    "RetriggerEntry",
    "TagReference",
    "TargetKind",
    "TenantCategory",
    "TenantContext",
    "ThresholdDefaults",
    "ThresholdSet",
    "TriggerEvidence",
    "TriggerSource",
    "VerdictHint",
    "freeze_map",
    "freeze_retrigger_map",
    "freeze_watch_map",
    "make_edge_key",
    "make_node_key",
    "parse_target_key",
]
