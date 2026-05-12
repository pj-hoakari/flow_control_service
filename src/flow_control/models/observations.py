"""Observation snapshots (module design v1 §3.4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .enums import ConfidenceFlag, FlowDirection


@dataclass(frozen=True)
class ArcFlow:
    edge_id: str
    direction: FlowDirection
    flow_rate: float
    confidence_flag: ConfidenceFlag = ConfidenceFlag.OK


@dataclass(frozen=True)
class ArcStagnation:
    edge_id: str
    stagnation: float
    confidence_flag: ConfidenceFlag = ConfidenceFlag.OK


@dataclass(frozen=True)
class ArcScalarFlow:
    edge_id: str
    observed_count: float
    confidence_flag: ConfidenceFlag = ConfidenceFlag.OK


@dataclass(frozen=True)
class NodeOccupancy:
    node_id: str
    occupancy: float
    confidence_flag: ConfidenceFlag = ConfidenceFlag.OK


@dataclass(frozen=True)
class Observations:
    observed_at: datetime
    arc_flows: tuple[ArcFlow, ...] = field(default_factory=tuple)
    arc_stagnations: tuple[ArcStagnation, ...] = field(default_factory=tuple)
    arc_scalar_flows: tuple[ArcScalarFlow, ...] = field(default_factory=tuple)
    node_occupancy: tuple[NodeOccupancy, ...] = field(default_factory=tuple)

    def stagnation_for(self, edge_id: str) -> ArcStagnation | None:
        for s in self.arc_stagnations:
            if s.edge_id == edge_id:
                return s
        return None
